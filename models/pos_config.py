from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class PosConfig(models.Model):
    _inherit = 'pos.config'

    hka_pos_code = fields.Char(
        string='HKA POS Code',
        help='Specific Point of Sale code for HKA integration (3 digits). If empty, will use branch default code.'
    )
    branch_id = fields.Many2one(
        'res.branch',
        string='Branch',
        domain="[('company_id', '=', company_id)]"
    )

    @api.constrains('hka_pos_code')
    def _check_hka_pos_code(self):
        for config in self:
            if config.hka_pos_code and (not config.hka_pos_code.isdigit() or len(config.hka_pos_code) != 3):
                raise ValidationError(_('HKA POS Code must be exactly 3 digits')) 