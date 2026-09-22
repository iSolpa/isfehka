from odoo import models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)

class PosOrder(models.Model):
    _inherit = 'pos.order'

    def _generate_pos_order_invoice(self):
        """Override to handle HKA integration when creating invoices from POS orders"""
        # Validate no mixed refund/sale lines when creating invoice
        # Skip discount lines (negative price_subtotal with positive qty) as they don't count as sales/returns
        has_positive = False
        has_negative = False
        for line in self.lines:
            # Skip discount lines - they have positive qty but negative subtotal
            if line.qty > 0 and line.price_subtotal < 0:
                continue
            if line.qty > 0:
                has_positive = True
            if line.qty < 0:
                has_negative = True
            if has_positive and has_negative:
                raise ValidationError(_(
                    'No se pueden generar facturas electrónicas que contengan '
                    'tanto devoluciones como ventas en la misma orden. '
                    'Por favor, separe la devolución y la venta en órdenes diferentes.'
                ))

        # Call super to create the invoice
        moves = super()._generate_pos_order_invoice()
        
        if not moves:
            return moves

        # Record the sale durably BEFORE attempting the electronic invoice. A failed FE
        # submission must never roll back (and lose) the POS order. With the order and its
        # posted invoice committed here, any cr.rollback() inside _send_to_hka can only
        # unwind the FE-send's own writes (its reserved fiscal number is reclaimed by
        # _release_fiscal_number as before) — never the sale itself.
        self.env.cr.commit()

        # Get the actual invoice record — fallback if _post() auto-send didn't fire
        invoice = moves if isinstance(moves, models.Model) else self.account_move
        if invoice:
            try:
                # Set HKA fields from POS config if not already sent
                if invoice.hka_status != 'sent':
                    invoice.write({
                        'tipo_documento': '04' if self.amount_total < 0 else self.config_id.hka_tipo_documento,
                        'naturaleza_operacion': '04' if self.amount_total < 0 else self.config_id.hka_naturaleza_operacion,
                    })
                    invoice._send_to_hka()
            except Exception as e:
                # A failed FE does NOT discard the sale. Keep the POS order and its posted
                # invoice (flagged hka_status='error') so revenue stays recorded and the FE
                # can be resent from the back office. Do not unlink, reset state, or raise —
                # _send_to_hka already rolled back only its own writes (down to the pre-FE
                # commit above), so the invoice survives; re-mark it error after that rollback.
                error_msg = str(e)
                _logger.error(
                    'HKA submission failed for invoice %s (kept for resend): %s',
                    (invoice.name if invoice.exists() else 'Unknown'),
                    error_msg,
                )
                if invoice.exists():
                    invoice.write({
                        'hka_status': 'error',
                        'hka_message': error_msg,
                    })
        
        return moves
