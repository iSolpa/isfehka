from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResBranch(models.Model):
    _name = 'res.branch'
    _description = 'Company Branch'

    name = fields.Char(string='Branch Name', required=True)
    code = fields.Char(
        string='Branch Code', 
        required=True,
        help='Code used for HKA integration (4 digits)'
    )
    default_pos_code = fields.Char(
        string='Default POS Code',
        required=True,
        help='Default Point of Sale code for HKA integration (3 digits)'
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)

    @api.constrains('code')
    def _check_code(self):
        for branch in self:
            if not branch.code.isdigit() or len(branch.code) != 4:
                raise ValidationError(_('Branch Code must be exactly 4 digits'))

    @api.constrains('default_pos_code')
    def _check_pos_code(self):
        for branch in self:
            if not branch.default_pos_code.isdigit() or len(branch.default_pos_code) != 3:
                raise ValidationError(_('Default POS Code must be exactly 3 digits'))
  