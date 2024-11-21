from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # HKA Fields
    isfehka_token_empresa = fields.Char(
        string='HKA Token Empresa',
        config_parameter='isfehka.token_empresa'
    )
    isfehka_token_password = fields.Char(
        string='HKA Token Password',
        config_parameter='isfehka.token_password'
    )
    isfehka_wsdl_url = fields.Char(
        string='HKA WSDL URL',
        config_parameter='isfehka.wsdl_url'
    )
    isfehka_test_mode = fields.Boolean(
        string='Test Mode',
        config_parameter='isfehka.test_mode'
    )
    
    isfehka_next_number = fields.Char(
        string='Próximo Número Fiscal HKA',
        config_parameter='isfehka.next_number',
        help='Próximo número de documento fiscal a utilizar (10 dígitos). '
             'Debe ser mayor que cualquier número ya utilizado en el sistema HKA.'
    )

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
                # Check if new number is less than current to prevent decreasing
                current = self.env['ir.config_parameter'].sudo().get_param('isfehka.next_number')
                # Only validate if the number is different from the current one
                if current and record.isfehka_next_number != current and int(record.isfehka_next_number) <= int(current):
                    raise ValidationError(_('El nuevo número fiscal debe ser mayor que el actual.'))

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(
            isfehka_token_empresa=ICP.get_param('isfehka.token_empresa'),
            isfehka_token_password=ICP.get_param('isfehka.token_password'),
            isfehka_wsdl_url=ICP.get_param('isfehka.wsdl_url'),
            isfehka_test_mode=ICP.get_param('isfehka.test_mode', 'False').lower() == 'true',
            isfehka_next_number=ICP.get_param('isfehka.next_number', '0000000001'),
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('isfehka.token_empresa', self.isfehka_token_empresa)
        ICP.set_param('isfehka.token_password', self.isfehka_token_password)
        ICP.set_param('isfehka.wsdl_url', self.isfehka_wsdl_url)
        ICP.set_param('isfehka.test_mode', str(self.isfehka_test_mode)) 
        ICP.set_param('isfehka.next_number', self.isfehka_next_number)