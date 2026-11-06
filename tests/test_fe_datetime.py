from datetime import datetime
from unittest.mock import patch

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestFeDatetime(AccountTestInvoicingCommon):
    """Dates exchanged with HKA (#2004). No test reaches HKA."""

    def _invoice(self, **vals):
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner_a.id,
            'invoice_line_ids': [(0, 0, {'name': 'x', 'quantity': 1, 'price_unit': 10})],
            **vals,
        })

    def test_parse_panama_offset_to_utc(self):
        parse = self.env['account.move']._parse_hka_datetime
        self.assertEqual(parse('2026-11-06T11:52:41-05:00'), datetime(2026, 11, 6, 16, 52, 41))

    def test_parse_utc_and_no_offset(self):
        parse = self.env['account.move']._parse_hka_datetime
        self.assertEqual(parse('2026-11-06T16:52:41Z'), datetime(2026, 11, 6, 16, 52, 41))
        self.assertEqual(parse('2026-11-06T11:52:41'), datetime(2026, 11, 6, 16, 52, 41))

    def test_parse_evening_crosses_utc_day(self):
        parse = self.env['account.move']._parse_hka_datetime
        self.assertEqual(parse('2026-11-06T21:30:00-05:00'), datetime(2026, 11, 7, 2, 30, 0))

    def test_parse_empty_and_invalid(self):
        parse = self.env['account.move']._parse_hka_datetime
        self.assertFalse(parse(''))
        self.assertFalse(parse(None))
        self.assertFalse(parse('not a date'))

    def test_emission_is_panama_time(self):
        move = self.env['account.move']
        self.assertEqual(
            move._get_panama_datetime_str(datetime(2026, 11, 7, 0, 1, 54)),
            '2026-11-06T19:01:54-05:00',
        )

    def test_send_stores_utc(self):
        invoice = self._invoice()
        invoice.numero_documento_fiscal = '0000000999'
        result = {'success': True, 'data': {
            'fechaRecepcionDGI': '2026-11-06T11:52:41-05:00', 'cufe': 'FE-TEST', 'qr': '',
            'nroProtocoloAutorizacion': '1',
        }}
        service = type(self.env['hka.service'])
        with patch.object(service, 'send_invoice', return_value=result), \
                patch.object(type(invoice), '_validate_hka_data', return_value=True), \
                patch.object(type(invoice), '_prepare_hka_data', return_value={}), \
                patch.object(self.env.cr, 'commit', lambda: None):
            invoice._send_to_hka()
        self.assertEqual(invoice.hka_fecha_recepcion_dgi, datetime(2026, 11, 6, 16, 52, 41))

    def test_credit_note_reference_is_panama_time(self):
        original = self._invoice(hka_cufe='FE-ORIG')
        original.hka_fecha_recepcion_dgi = datetime(2026, 2, 27, 0, 0, 12)  # 19:00:12 Panama
        note = self._invoice(move_type='out_refund', reversed_entry_id=original.id, tipo_documento='04')
        cls = type(note)
        with patch.object(cls, '_prepare_hka_client_data', return_value={}), \
                patch.object(cls, '_prepare_hka_items_data', return_value=[]), \
                patch.object(cls, '_prepare_hka_totals_data', return_value={}):
            data = note._prepare_hka_data()
        ref = data['documento']['datosTransaccion']['listaDocsFiscalReferenciados']['docFiscalReferenciado'][0]
        self.assertEqual(ref['fechaEmisionDocFiscalReferenciado'], '2026-02-26T19:00:12-05:00')
