from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = 'res.company'

    hka_branch_code = fields.Char(
        string='HKA Branch Code',
        default='0000',
        help='Branch code for HKA integration (4 digits)'
    )

    @api.constrains('hka_branch_code')
    def _check_hka_branch_code(self):
        for company in self:
            if company.hka_branch_code and (not company.hka_branch_code.isdigit() or len(company.hka_branch_code) != 4):
                raise ValidationError(_('HKA Branch Code must be exactly 4 digits'))