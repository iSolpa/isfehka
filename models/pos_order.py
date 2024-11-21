from odoo import models, _
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        moves = super()._generate_pos_order_invoice()
        
        # Ensure we have a proper recordset
        if isinstance(moves, list):
            moves = self.env['account.move'].browse(moves)
        
        # Send each created invoice to HKA
        for move in moves:
            try:
                move._send_to_hka()
            except Exception as e:
                # Log error but don't stop the process
                _logger.warning(
                    'Invoice %s created but failed to send to HKA: %s',
                    move.name, str(e)
                )
        
        return moves
