# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools.misc import format_date


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _get_rendering_context(self, report, docids, data):
        """Ensure format_date helper is always available in QWeb report context.
        
        This fixes a KeyError: 'format_date' issue in Odoo 19 when rendering
        invoice PDFs during POS order processing where the helper was missing.
        """
        res = super()._get_rendering_context(report, docids, data)
        if 'format_date' not in res:
            res['format_date'] = lambda date, date_format=False, lang_code=False: format_date(
                self.env, date, date_format=date_format, lang_code=lang_code
            )
        return res
