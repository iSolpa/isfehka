from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    isfehka_configuration_id = fields.Many2one(
        'isfehka.configuration',
        string='HKA Configuration',
        domain="[('active', '=', True)]",
        help='Conjunto de credenciales HKA que utilizará la compañía seleccionada.'
    )
    isfehka_token_empresa = fields.Char(string='HKA Token Empresa')
    isfehka_token_password = fields.Char(string='HKA Token Password')
    isfehka_wsdl_url = fields.Char(string='HKA WSDL URL')
    isfehka_test_mode = fields.Boolean(string='Test Mode')
    isfehka_default_tipo_documento = fields.Selection([
        ('01', 'Factura de Operación Interna'),
        ('02', 'Factura de Importación'),
        ('03', 'Factura de Exportación'),
        ('04', 'Nota de Crédito'),
        ('05', 'Nota de Débito'),
        ('06', 'Nota de Crédito Genérica'),
        ('07', 'Nota de Débito Genérica'),
        ('08', 'Factura de Zona Franca'),
        ('09', 'Factura de Reembolso')
    ], string='Tipo de Documento por Defecto',
       default='01',
       help='Tipo de documento por defecto para facturas generadas desde ventas/facturas')
    isfehka_next_number = fields.Char(
        string='Próximo Número Fiscal HKA',
        help='Próximo número de documento fiscal a utilizar (10 dígitos). '
             'Debe ser mayor que cualquier número ya utilizado en el sistema HKA.'
    )

    @api.onchange('isfehka_configuration_id')
    def _onchange_isfehka_configuration_id(self):
        config = self.isfehka_configuration_id
        if config:
            self.isfehka_token_empresa = config.token_empresa
            self.isfehka_token_password = config.token_password
            self.isfehka_wsdl_url = config.wsdl_url
            self.isfehka_test_mode = config.test_mode
            self.isfehka_default_tipo_documento = config.default_tipo_documento
            self.isfehka_next_number = config.next_number
        else:
            self.isfehka_token_empresa = False
            self.isfehka_token_password = False
            self.isfehka_wsdl_url = False
            self.isfehka_test_mode = False
            self.isfehka_default_tipo_documento = '01'
            self.isfehka_next_number = '0000000001'

    @api.constrains('isfehka_next_number')
    def _check_isfehka_next_number(self):
        for record in self:
            if record.isfehka_next_number:
                if not record.isfehka_next_number.isdigit():
                    raise ValidationError(_('El número fiscal debe contener solo dígitos.'))
                if len(record.isfehka_next_number) != 10:
                    raise ValidationError(_('El número fiscal debe tener exactamente 10 dígitos.'))
                if int(record.isfehka_next_number) < 1:
                    raise ValidationError(_('El número fiscal debe ser mayor que 0.'))
                # Prevent decreasing below current configuration value
                company = record.company_id or record.env.company
                config = record.isfehka_configuration_id or company.hka_configuration_id
                if config and config.next_number and record.isfehka_next_number != config.next_number:
                    if int(record.isfehka_next_number) <= int(config.next_number):
                        raise ValidationError(_('El nuevo número fiscal debe ser mayor que el actual.'))

    @api.model
    def get_values(self):
        res = super().get_values()
        company = self.company_id or self.env.company
        config = company.hka_configuration_id
        res.update(
            isfehka_configuration_id=config.id if config else False,
            isfehka_token_empresa=config.token_empresa if config else False,
            isfehka_token_password=config.token_password if config else False,
            isfehka_wsdl_url=config.wsdl_url if config else False,
            isfehka_test_mode=config.test_mode if config else False,
            isfehka_default_tipo_documento=config.default_tipo_documento if config else '01',
            isfehka_next_number=config.next_number if config else '0000000001',
        )
        return res

    def set_values(self):
        super().set_values()
        company = self.company_id or self.env.company
        config = self.isfehka_configuration_id

        # Create configuration if none selected but values provided
        if not config and self.isfehka_token_empresa and self.isfehka_token_password:
            config_vals = {
                'name': '%s - HKA' % company.display_name,
                'token_empresa': self.isfehka_token_empresa,
                'token_password': self.isfehka_token_password,
                'wsdl_url': self.isfehka_wsdl_url or self.env['isfehka.configuration']._default_wsdl_url(),
                'test_mode': self.isfehka_test_mode,
                'default_tipo_documento': self.isfehka_default_tipo_documento or '01',
                'next_number': self.isfehka_next_number or '0000000001',
            }
            config = self.env['isfehka.configuration'].create(config_vals)

        if config:
            config.write({
                'token_empresa': self.isfehka_token_empresa,
                'token_password': self.isfehka_token_password,
                'wsdl_url': self.isfehka_wsdl_url,
                'test_mode': self.isfehka_test_mode,
                'default_tipo_documento': self.isfehka_default_tipo_documento or '01',
                'next_number': self.isfehka_next_number or '0000000001',
            })
            company.write({'hka_configuration_id': config.id})
        else:
            company.write({'hka_configuration_id': False})
