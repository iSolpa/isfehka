from odoo import models, _
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        # Call super to create the invoice
        moves = super()._generate_pos_order_invoice()
        
        if not moves:
            return moves

        # Get the actual invoice record
        if not isinstance(moves, models.Model):
            invoice = self.account_move_id
            if invoice:
                try:
                    invoice._send_to_hka()
                except Exception as e:
                    _logger.warning(
                        'Invoice %s created but failed to send to HKA: %s',
                        invoice.name or 'Unknown',
                        str(e)
                    )
        
        return moves
