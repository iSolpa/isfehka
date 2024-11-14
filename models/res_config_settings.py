from odoo import models, fields, api

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

    # Required field from account module to avoid the error
    account_tax_periodicity = fields.Selection(
        related='company_id.account_tax_periodicity',
        readonly=False
    )
    account_tax_periodicity_reminder_day = fields.Integer(
        related='company_id.account_tax_periodicity_reminder_day',
        readonly=False
    )
    account_tax_periodicity_journal_id = fields.Many2one(
        related='company_id.account_tax_periodicity_journal_id',
        readonly=False
    )

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(
            isfehka_token_empresa=ICP.get_param('isfehka.token_empresa'),
            isfehka_token_password=ICP.get_param('isfehka.token_password'),
            isfehka_wsdl_url=ICP.get_param('isfehka.wsdl_url'),
            isfehka_test_mode=ICP.get_param('isfehka.test_mode', 'False').lower() == 'true',
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('isfehka.token_empresa', self.isfehka_token_empresa)
        ICP.set_param('isfehka.token_password', self.isfehka_token_password)
        ICP.set_param('isfehka.wsdl_url', self.isfehka_wsdl_url)
        ICP.set_param('isfehka.test_mode', str(self.isfehka_test_mode)) 