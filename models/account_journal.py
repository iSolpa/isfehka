from odoo import models, fields, api

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    branch_id = fields.Many2one(
        'res.branch',
        string='Branch',
        domain="[('company_id', '=', company_id)]"
    )