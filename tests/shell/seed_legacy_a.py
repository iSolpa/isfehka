# Seed a legacy isfehka DB simulating the PROD (17-main) shape:
# isfehka_configuration table + res_company.hka_configuration_id link.
# Run with the OLD isfehka code via odoo shell.
import base64
import traceback

try:
    company = env.company

    # Chart of accounts for invoicing
    if not env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1):
        env['account.chart.template'].try_loading('pa', company)
    journal = env['account.journal'].search([('type', '=', 'sale'), ('company_id', '=', company.id)], limit=1)
    assert journal

    # --- 17-shape configuration table (manufactured at SQL level: the
    # migration only sees the schema, not the old ORM) ---
    env.cr.execute("""
        CREATE TABLE IF NOT EXISTS isfehka_configuration (
            id serial PRIMARY KEY,
            name varchar NOT NULL,
            active boolean,
            token_empresa varchar,
            token_password varchar,
            wsdl_url varchar,
            test_mode boolean,
            default_tipo_documento varchar,
            next_number varchar,
            create_uid integer, create_date timestamp,
            write_uid integer, write_date timestamp)
    """)
    env.cr.execute("""
        INSERT INTO isfehka_configuration
            (id, name, active, token_empresa, token_password, wsdl_url,
             test_mode, default_tipo_documento, next_number,
             create_uid, create_date, write_uid, write_date)
        VALUES (1, 'HKA Inversora', true, 'TOKEMP-LEGACY', 'TOKPWD-LEGACY',
                'https://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc?singleWsdl',
                true, '01', '0000000027', 1, now(), 1, now())
        ON CONFLICT (id) DO NOTHING
    """)
    env.cr.execute("ALTER TABLE res_company ADD COLUMN IF NOT EXISTS hka_configuration_id integer")
    env.cr.execute("ALTER TABLE res_company ADD COLUMN IF NOT EXISTS hka_auto_send_on_post boolean")
    env.cr.execute("UPDATE res_company SET hka_configuration_id = 1, hka_auto_send_on_post = true WHERE id = %s", [company.id])

    # ICP params also present (must be ignored by the table branch but cleaned)
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_param('isfehka.token_empresa', 'ICP-TOKEN-SHOULD-BE-IGNORED')
    ICP.set_param('isfehka.next_number', '0000000099')

    # --- partner with geo ---
    st = env['res.country.state'].search([('country_id.code', '=', 'PA')], limit=1)
    dist = env['res.distrito.pa'].search([('state_id', '=', st.id)], limit=1)
    corr = env['res.corregimiento.pa'].search([('distrito_id', '=', dist.id)], limit=1)
    partner = env['res.partner'].create({
        'name': 'Cliente Legado', 'ruc': '8-123-456', 'dv': '21',
        'tipo_contribuyente': '2', 'tipo_cliente_fe': '01', 'street': 'Calle 2',
        'state_id': st.id, 'l10n_pa_distrito_id': dist.id,
        'l10n_pa_corregimiento_id': corr.id,
    })
    partner.write({'ruc_verified': True})
    env.cr.execute("SELECT COUNT(*) FROM res_distrito_pa")
    distrito_count = env.cr.fetchone()[0]

    prod = env['product.product'].create({'name': 'Producto Legado', 'lst_price': 10.0})
    inv = env['account.move'].with_context(isfe_skip_autosend=True).create({
        'move_type': 'out_invoice', 'partner_id': partner.id, 'journal_id': journal.id,
        'invoice_line_ids': [(0, 0, {'product_id': prod.id, 'quantity': 1, 'price_unit': 10.0})],
    })
    # Simulate an FE-sent legacy document (two writes -> tracking history)
    inv.write({'hka_status': 'sent',
               'hka_cufe': 'FE0120000155704849-2-2021-86530126TESTCUFE',
               'numero_documento_fiscal': '0000000026',
               'hka_message': 'Documento enviado exitosamente',
               'hka_pdf': base64.b64encode(b'%PDF-FAKE-LEGACY'),
               'hka_pdf_filename': 'FACT_0000000026.pdf'})
    env['account.move'].flush_model()
    env.cr.commit()

    # POS payment method with legacy HKA code 02 = Efectivo
    pm = env['pos.payment.method'].create({'name': 'Efectivo HKA', 'hka_payment_type': '02'})

    env.cr.execute("""SELECT COUNT(*) FROM ir_attachment
                      WHERE res_model='account.move' AND res_field='hka_pdf'""")
    att = env.cr.fetchone()[0]
    env.cr.execute("""SELECT COUNT(*) FROM mail_tracking_value v
                      JOIN ir_model_fields f ON f.id = v.field_id
                      WHERE f.model='account.move' AND f.name='hka_status'""")
    trk = env.cr.fetchone()[0]
    print('SEED-A OK: inv=%s att_hka_pdf=%s tracking_hka_status=%s distritos=%s pm=%s'
          % (inv.id, att, trk, distrito_count, pm.id))
    env.cr.commit()
except Exception as e:
    traceback.print_exc()
    print('SEED-A FAILED:', e)
    env.cr.rollback()
