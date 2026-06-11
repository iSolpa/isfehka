# Seed a legacy isfehka DB in the legacy-18 ICP shape (no config table).
import traceback
try:
    ICP = env['ir.config_parameter'].sudo()
    ICP.set_param('isfehka.token_empresa', 'ICP-TOKEN')
    ICP.set_param('isfehka.token_password', 'ICP-PWD')
    ICP.set_param('isfehka.wsdl_url', 'https://demoemision.thefactoryhka.com.pa/ws')
    ICP.set_param('isfehka.test_mode', 'True')
    ICP.set_param('isfehka.default_tipo_documento', '01')
    ICP.set_param('isfehka.next_number', '0000059446')
    env.cr.commit()
    print('SEED-B OK')
except Exception as e:
    traceback.print_exc()
    print('SEED-B FAILED:', e)
    env.cr.rollback()
