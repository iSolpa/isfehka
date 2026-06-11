# Verify the legacy->2.0 migration outcome on mig-a (run with NEW code).
import base64
import traceback

def ok(name):
    print('PASS:', name)

try:
    env.cr.execute("SELECT id FROM account_move WHERE fe_cufe LIKE 'FE0120%'")
    row = env.cr.fetchone()
    assert row, 'migrated invoice not found by fe_cufe'
    inv = env['account.move'].browse(row[0])
    assert inv.fe_status == 'sent', inv.fe_status
    assert inv.numero_documento_fiscal == '0000000026'
    assert inv.fe_message == 'Documento enviado exitosamente'
    ok('account.move: fe_status/fe_cufe/numero/mensaje preserved')

    assert inv.fe_pdf, 'fe_pdf attachment lost'
    assert base64.b64decode(inv.fe_pdf).startswith(b'%PDF-FAKE-LEGACY')
    assert inv.fe_pdf_filename == 'FACT_0000000026.pdf'
    env.cr.execute("""SELECT COUNT(*) FROM ir_attachment
                      WHERE res_model='account.move' AND res_field='hka_pdf'""")
    assert env.cr.fetchone()[0] == 0
    ok('attachment remapped hka_pdf -> fe_pdf, content intact')

    env.cr.execute("""SELECT column_name FROM information_schema.columns
                      WHERE table_name='account_move' AND column_name LIKE 'hka\\_%'""")
    assert not env.cr.fetchall(), 'legacy hka_* columns remain'
    ok('no legacy hka_* columns on account_move')

    conf = env['isfe.configuration'].browse(1)
    assert conf.exists() and conf.driver == 'hka', (conf.exists(), conf.driver)
    assert conf.next_number == '0000000027', conf.next_number
    assert conf.hka_token_empresa == 'TOKEMP-LEGACY'
    assert conf.hka_token_password == 'TOKPWD-LEGACY'
    assert conf.hka_wsdl_url and 'thefactoryhka' in conf.hka_wsdl_url
    ok('configuration copied: id/counter/credentials/driver preserved')

    company = env['res.company'].browse(1)
    assert company.fe_configuration_id.id == 1
    assert conf.company_id.id == company.id, conf.company_id
    assert company.fe_auto_send_on_post is True
    ok('company link + auto-send + single-company ownership')

    drv = env['isfe.configuration']._resolve_driver(company)
    assert drv._name == 'isfe.driver.hka', drv._name
    ok('per-company dispatch resolves isfe.driver.hka')

    pm = env['pos.payment.method'].search([('name', '=', 'Efectivo HKA')], limit=1)
    assert pm and pm.fe_payment_type == '01', (pm, pm.fe_payment_type)
    ok("payment method value remap: HKA '02' Efectivo -> neutral '01'")

    env.cr.execute("SELECT COUNT(*) FROM res_distrito_pa")
    assert env.cr.fetchone()[0] == 69, 'geo catalog duplicated or lost'
    env.cr.execute("""SELECT COUNT(*) FROM ir_model_data
                      WHERE module='isfehka' AND model IN
                      ('res.distrito.pa','res.corregimiento.pa','res.country.state')""")
    assert env.cr.fetchone()[0] == 0
    env.cr.execute("""SELECT COUNT(*) FROM ir_model_data
                      WHERE module='isfe_base' AND model='res.distrito.pa'""")
    assert env.cr.fetchone()[0] == 69
    ok('geo catalogs: no duplicates, xmlids adopted by isfe_base (69 distritos)')

    env.cr.execute("SELECT COUNT(*) FROM ir_config_parameter WHERE key LIKE 'isfehka.%'")
    assert env.cr.fetchone()[0] == 0
    ok('legacy isfehka.* config parameters cleaned')

    env.cr.execute("""SELECT 1 FROM information_schema.tables
                      WHERE table_name='isfehka_configuration_legacy_bak'""")
    assert env.cr.fetchone()
    ok('legacy config table kept as rollback artifact')

    admin = env.ref('base.user_admin')
    assert admin in env.ref('isfe_base.group_isfe_manager').users
    env.cr.execute("""SELECT COUNT(*) FROM ir_model_data
                      WHERE module='isfehka' AND model='res.groups'""")
    assert env.cr.fetchone()[0] == 0
    ok('group membership migrated to isfe_base groups; legacy groups swept')

    partner = env['res.partner'].search([('name', '=', 'Cliente Legado')], limit=1)
    assert partner.ruc == '8-123-456' and partner.codigo_ubicacion
    ok('partner fiscal + geo intact')

    # Functional sanity on the upgraded registry: NC derivation still works.
    refund = env['account.move'].create({
        'move_type': 'out_refund', 'partner_id': partner.id,
        'reversed_entry_id': inv.id,
        'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 5.0})],
    })
    assert refund.tipo_documento == '04', refund.tipo_documento
    doc = refund._prepare_fe_document()
    payload = env['isfe.driver.hka']._build_hka_documento(doc)
    assert payload['datosTransaccion']['tipoDocumento'] == '04'
    assert payload['datosTransaccion']['listaDocsFiscalReferenciados']['docFiscalReferenciado'][0]['cufeFEReferenciada'] == inv.fe_cufe
    ok('post-upgrade functional: NC 04 + HKA payload references legacy CUFE')

    print('VERIFY-A: ALL PASSED')
except Exception as e:
    traceback.print_exc()
    print('VERIFY-A FAILED:', e)
finally:
    env.cr.rollback()
