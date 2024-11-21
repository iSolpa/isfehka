from odoo import models, _
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        # Call super to create the invoice
        result = super()._generate_pos_order_invoice()
        
        # If no invoice was created, return early
        if not result:
            return result
            
        # Get the created invoice(s)
        if isinstance(result, list):
            invoice_ids = result
        else:
            invoice_ids = [result]
            
        # Get the invoice records
        moves = self.env['account.move'].browse(invoice_ids)
        
        # Send each created invoice to HKA
        for move in moves:
            try:
                if hasattr(move, '_send_to_hka'):
                    move._send_to_hka()
            except Exception as e:
                # Log error but don't stop the process
                _logger.warning(
                    'Invoice %s created but failed to send to HKA: %s',
                    move.display_name if hasattr(move, 'display_name') else 'Unknown',
                    str(e)
                )
        
        return result
