from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    hka_branch_code = fields.Char(
        string='HKA Branch Code',
        default='0000',
        help='Branch code for HKA integration (4 digits)'
    )

    hka_pos_code = fields.Char(
        string='HKA POS Code',
        default='001',
        help='Default Point of Sale code for HKA integration (3 digits). Used when POS module is not installed.'
    )

    @api.constrains('hka_branch_code', 'hka_pos_code')
    def _check_hka_codes(self):
        for company in self:
            if company.hka_branch_code and (not company.hka_branch_code.isdigit() or len(company.hka_branch_code) != 4):
                raise ValidationError(_('HKA Branch Code must be exactly 4 digits'))
            if company.hka_pos_code and (not company.hka_pos_code.isdigit() or len(company.hka_pos_code) != 3):
                raise ValidationError(_('HKA POS Code must be exactly 3 digits'))