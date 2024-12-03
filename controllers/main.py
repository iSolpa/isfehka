from odoo import http
from odoo.http import request
import logging
import base64

_logger = logging.getLogger(__name__)

class PosHkaController(http.Controller):
    @http.route('/pos/get_order_invoice', type='json', auth='user')
    def get_order_invoice(self, pos_reference):
        _logger.info('[HKA Debug] Getting invoice for POS reference: %s', pos_reference)
        try:
            order = request.env['pos.order'].search([('pos_reference', '=', pos_reference)], limit=1)
            if not order:
                _logger.warning('[HKA Debug] No order found for reference: %s', pos_reference)
                return {'error': 'Order not found'}
            
            _logger.info('[HKA Debug] Found order: %s', order.name)
            if not order.account_move:
                _logger.warning('[HKA Debug] No invoice found for order: %s', order.name)
                return {'error': 'No invoice found for order'}
            
            _logger.info('[HKA Debug] Found invoice: %s', order.account_move.id)
            return {
                'success': True,
                'invoice_id': order.account_move.id,
                'order_name': order.name,
                'pos_reference': order.pos_reference
            }
        except Exception as e:
            _logger.error('[HKA Debug] Error in get_order_invoice: %s', str(e))
            return {'error': str(e)}

    @http.route('/pos/get_hka_pdf', type='json', auth='user')
    def get_hka_pdf(self, invoice_id):
        _logger.info('[HKA Debug] Getting HKA PDF for invoice: %s', invoice_id)
        try:
            invoice = request.env['account.move'].browse(int(invoice_id))
            if not invoice.exists():
                _logger.warning('[HKA Debug] Invoice not found: %s', invoice_id)
                return {'error': 'Invoice not found'}

            _logger.info('[HKA Debug] Found invoice: %s', invoice.name)
            if not invoice.hka_pdf:
                _logger.warning('[HKA Debug] No HKA PDF found for invoice: %s', invoice.name)
                return {'error': 'No HKA PDF found for invoice'}

            _logger.info('[HKA Debug] Converting HKA PDF to image')
            import fitz  # PyMuPDF
            pdf_data = base64.b64decode(invoice.hka_pdf)
            doc = fitz.open(stream=pdf_data, filetype="pdf")
            page = doc[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")
            
            image_base64 = base64.b64encode(img_data).decode('utf-8')
            _logger.info('[HKA Debug] Successfully converted PDF to image. Data length: %d', len(image_base64))
            
            return {
                'success': True,
                'image_data': f'data:image/png;base64,{image_base64}'
            }
        except Exception as e:
            _logger.error('[HKA Debug] Error in get_hka_pdf: %s', str(e))
            return {'error': str(e)}
