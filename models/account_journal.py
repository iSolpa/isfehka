from odoo import models, fields, _


class AccountJournal(models.Model):
    _inherit = 'account.journal'

    hka_payment_type = fields.Selection([
        ('01', 'Crédito'),
        ('02', 'Efectivo'),
        ('03', 'Tarjeta Crédito'),
        ('04', 'Tarjeta Débito'),
        ('05', 'Tarjeta Fidelización'),
        ('06', 'Vale'),
        ('07', 'Tarjeta de Regalo'),
        ('08', 'Transf/Deposito cta. Bancaria'),
        ('09', 'Cheque'),
        ('99', 'Otro')
    ], string='HKA Payment Type', 
       help='Map this journal to HKA payment type for electronic invoicing. '
            'This is used when registering payments on invoices from sales orders.')
