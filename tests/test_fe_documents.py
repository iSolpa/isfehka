import base64
from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged

PDF = b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj <</Type /Catalog>> endobj\n%%EOF\n'
XML = b'<?xml version="1.0" encoding="utf-8"?>\n<rFE><dFechaEm>2026-11-06T17:37:52-05:00</dFechaEm></rFE>'


@tagged('post_install', '-at_install')
class TestFeDocuments(AccountTestInvoicingCommon):
    """Documents fetched after sending (POS path). No test reaches HKA."""

    def test_retrieved_documents_are_stored_intact(self):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 10})],
        })
        move.write({'hka_status': 'sent', 'numero_documento_fiscal': '0000000001'})
        Service = type(self.env['hka.service'])
        Move = type(move)
        with patch.object(Service, 'get_pdf_document', return_value=PDF), \
                patch.object(Service, 'get_xml_document', return_value=XML), \
                patch.object(Move, '_get_hka_branch', return_value='0000'), \
                patch.object(Move, '_get_hka_pos_code', return_value='001'):
            move.action_get_documents()
        move.invalidate_recordset(['hka_pdf', 'hka_xml'])
        self.assertEqual(base64.b64decode(move.hka_pdf), PDF)
        self.assertEqual(base64.b64decode(move.hka_xml), XML)
