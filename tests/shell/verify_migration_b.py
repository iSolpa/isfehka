# Verify the ICP-shape migration outcome on mig-b (run with NEW code).
import traceback
try:
    conf = env['isfe.configuration'].search([('driver', '=', 'hka')], limit=1)
    assert conf, 'no migrated config from ICP params'
    assert conf.hka_token_empresa == 'ICP-TOKEN'
    assert conf.hka_token_password == 'ICP-PWD'
    assert conf.next_number == '0000059446', conf.next_number
    assert conf.test_mode is True
    assert not conf.company_id, 'ICP-shape config must stay shared/global'
    print('PASS: ICP globals migrated into shared isfe.configuration (counter intact)')

    companies = env['res.company'].search([])
    assert all(c.fe_configuration_id.id == conf.id for c in companies)
    print('PASS: every company linked to the migrated config')

    env.cr.execute("SELECT COUNT(*) FROM ir_config_parameter WHERE key LIKE 'isfehka.%'")
    assert env.cr.fetchone()[0] == 0
    print('PASS: legacy ICP params cleaned')

    drv = env['isfe.configuration']._resolve_driver(companies[0])
    assert drv._name == 'isfe.driver.hka'
    print('PASS: dispatch resolves isfe.driver.hka')
    print('VERIFY-B: ALL PASSED')
except Exception as e:
    traceback.print_exc()
    print('VERIFY-B FAILED:', e)
finally:
    env.cr.rollback()
