from datetime import date, datetime
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestHkaDates(TransactionCase):
    """Dates in the HKA payload (#2004). No test reaches HKA."""

    def _documento(self, **doc):
        driver = self.env['isfe.driver.hka']
        cls = type(driver)
        with patch.object(cls, '_build_items', return_value=[]), \
                patch.object(cls, '_build_client', return_value={}), \
                patch.object(cls, '_build_totals', return_value={}):
            return driver._build_hka_documento(doc)

    def test_emission_after_19h_keeps_the_panama_day(self):
        data = self._documento(issue_datetime=datetime(2026, 11, 7, 0, 1, 54))
        transaction = data['datosTransaccion']
        self.assertEqual(transaction['fechaEmision'], '2026-11-06T19:01:54-05:00')
        self.assertEqual(transaction['fechaSalida'], '2026-11-06T19:01:54-05:00')

    def test_credit_note_reference_converts_utc(self):
        data = self._documento(
            issue_datetime=datetime(2026, 11, 7, 0, 1, 54), doc_type='04',
            reference={'cufe': 'FE-ORIG', 'date': datetime(2026, 2, 27, 0, 0, 12)})
        ref = data['datosTransaccion']['listaDocsFiscalReferenciados']['docFiscalReferenciado'][0]
        self.assertEqual(ref['fechaEmisionDocFiscalReferenciado'], '2026-02-26T19:00:12-05:00')

    def test_credit_note_reference_plain_date(self):
        data = self._documento(
            issue_datetime=datetime(2026, 11, 7, 0, 1, 54), doc_type='04',
            reference={'cufe': 'FE-ORIG', 'date': date(2026, 2, 27)})
        ref = data['datosTransaccion']['listaDocsFiscalReferenciados']['docFiscalReferenciado'][0]
        self.assertEqual(ref['fechaEmisionDocFiscalReferenciado'], '2026-02-27T00:00:00-05:00')
