from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    ICP = env['ir.config_parameter'].sudo()

    token_empresa = ICP.get_param('isfehka.token_empresa')
    token_password = ICP.get_param('isfehka.token_password')
    if not (token_empresa and token_password):
        return

    wsdl_url = ICP.get_param('isfehka.wsdl_url') or env['isfehka.configuration']._default_wsdl_url()
    default_tipo = ICP.get_param('isfehka.default_tipo_documento') or '01'
    next_number = ICP.get_param('isfehka.next_number') or '0000000001'
    test_mode = str(ICP.get_param('isfehka.test_mode')).lower() == 'true'

    if not next_number.isdigit() or len(next_number) != 10:
        next_number = '0000000001'

    config_vals = {
        'name': 'Migrated HKA Configuration',
        'token_empresa': token_empresa,
        'token_password': token_password,
        'wsdl_url': wsdl_url,
        'test_mode': test_mode,
        'default_tipo_documento': default_tipo if default_tipo in dict(env['isfehka.configuration']._fields['default_tipo_documento'].selection) else '01',
        'next_number': next_number,
    }

    config = env['isfehka.configuration'].sudo().search([
        ('token_empresa', '=', token_empresa),
        ('token_password', '=', token_password),
        ('wsdl_url', '=', wsdl_url),
    ], limit=1)
    if not config:
        config = env['isfehka.configuration'].sudo().create(config_vals)
    else:
        config.write(config_vals)

    env['res.company'].sudo().search([('hka_configuration_id', '=', False)]).write({'hka_configuration_id': config.id})
