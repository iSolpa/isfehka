from odoo import models, fields, api, _
from odoo.exceptions import UserError

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        moves = super()._generate_pos_order_invoice()
        
        # Send each created invoice to HKA
        for move in moves:
            try:
                move._send_to_hka()
            except Exception as e:
                # Log error but don't stop the process
                self.env.user.notify_warning(
                    title=_('HKA Integration Warning'),
                    message=_('Invoice %s created but failed to send to HKA: %s') % (move.name, str(e))
                )
        
        return moves
