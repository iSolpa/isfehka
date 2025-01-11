from odoo import models, _
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        # Validate no mixed refund/sale lines when creating invoice
        has_positive = False
        has_negative = False
        for line in self.lines:
            if line.qty > 0:
                has_positive = True
            if line.qty < 0:
                has_negative = True
            if has_positive and has_negative:
                raise models.ValidationError(_(
                    'No se pueden generar facturas electrónicas que contengan '
                    'tanto devoluciones como ventas en la misma orden. '
                    'Por favor, separe la devolución y la venta en órdenes diferentes.'
                ))

        # Call super to create the invoice
        moves = super()._generate_pos_order_invoice()
        
        if not moves:
            return moves

        # Get the actual invoice record
        if not isinstance(moves, models.Model):
            invoice = self.account_move
            if invoice:
                try:
                    # Set HKA fields from POS config, handling refunds properly
                    invoice.write({
                        'tipo_documento': '04' if self.amount_total < 0 else self.config_id.hka_tipo_documento,
                        'naturaleza_operacion': '04' if self.amount_total < 0 else self.config_id.hka_naturaleza_operacion,
                    })
                    # Send to HKA
                    invoice._send_to_hka()
                except Exception as e:
                    error_msg = str(e)
                    _logger.error(
                        'Failed to send invoice %s to HKA: %s',
                        invoice.name or 'Unknown',
                        error_msg
                    )
                    # Mark invoice as error and store the message
                    invoice.write({
                        'hka_status': 'error',
                        'hka_message': error_msg
                    })
                    # Delete the invoice since it failed HKA validation
                    invoice.button_draft()
                    invoice.button_cancel()
                    invoice.unlink()
                    # Reset POS order state
                    self.write({
                        'state': 'draft',
                        'account_move': False,
                    })
                    # Raise error to prevent completion
                    raise models.ValidationError(_(
                        'Error al enviar la factura a HKA. Por favor contacte al administrador.\n\n'
                        'Detalles: %s'
                    ) % error_msg)
        
        return moves
