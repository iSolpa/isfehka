from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class PosHkaController(http.Controller):
    @http.route('/pos/get_order_invoice', type='json', auth='user')
    def get_order_invoice(self, pos_reference):
        _logger.info("[HKA Debug] Searching for POS order with reference: %s", pos_reference)
        
        # First, let's see what orders exist in the system
        recent_orders = request.env['pos.order'].search([], limit=5, order='id desc')
        _logger.info("[HKA Debug] Recent orders in system:")
        for order in recent_orders:
            _logger.info("Order: name=%s, pos_reference=%s, pos_session_id=%s", 
                        order.name, order.pos_reference, order.session_id.name)
        
        # Now try to find our specific order
        domain = [
            '|', '|',
            ('name', '=', pos_reference),
            ('pos_reference', '=', pos_reference),
            ('pos_reference', 'ilike', pos_reference)
        ]
        
        pos_order = request.env['pos.order'].search(domain, limit=1)
        _logger.info("[HKA Debug] Search domain: %s", domain)
        _logger.info("[HKA Debug] Found POS order: %s", pos_order)
        
        if pos_order:
            _logger.info("[HKA Debug] Order details: name=%s, pos_reference=%s", 
                        pos_order.name, pos_order.pos_reference)
            
            # Get the invoice - try both new and old field names
            invoice = None
            if hasattr(pos_order, 'account_move'):
                invoice = pos_order.account_move
            elif hasattr(pos_order, 'invoice_id'):
                invoice = pos_order.invoice_id
            elif hasattr(pos_order, 'account_move_id'):
                invoice = pos_order.account_move_id
                
            _logger.info("[HKA Debug] Found invoice: %s", invoice)
            
            if invoice:
                return {
                    'invoice_id': invoice.id,
                    'success': True,
                    'order_name': pos_order.name,
                    'pos_reference': pos_order.pos_reference
                }
            else:
                return {'error': 'No invoice found for this order'}
        
        return {'error': 'POS order not found', 'reference_tried': pos_reference}

    @http.route('/pos/get_hka_pdf', type='json', auth='user')
    def get_hka_pdf(self, invoice_id):
        invoice = request.env['account.move'].browse(int(invoice_id))
        if not invoice.exists():
            return {'error': 'Invoice not found'}
        
        _logger.info("[HKA Debug] Getting PDF for invoice: %s", invoice.name)
        
        # Get HKA PDF data from the invoice
        hka_pdf_data = invoice.hka_pdf if hasattr(invoice, 'hka_pdf') else None
        
        if not hka_pdf_data:
            _logger.warning("[HKA Debug] No PDF data found for invoice %s", invoice.name)
            return {
                'error': 'No PDF data found',
                'success': False
            }
            
        _logger.info("[HKA Debug] Found PDF data for invoice %s", invoice.name)
        return {
            'pdf_data': hka_pdf_data,
            'success': True
        }