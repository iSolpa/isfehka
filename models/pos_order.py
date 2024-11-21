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
            invoice = self.account_move
            if invoice:
                try:
                    # Set HKA fields from POS config
                    invoice.write({
                        'tipo_documento': self.config_id.hka_tipo_documento,
                        'naturaleza_operacion': self.config_id.hka_naturaleza_operacion,
                    })
                    # Send to HKA
                    invoice._send_to_hka()
                except Exception as e:
                    _logger.warning(
                        'Invoice %s created but failed to send to HKA: %s',
                        invoice.name or 'Unknown',
                        str(e)
                    )
        
        return moves
