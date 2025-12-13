# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools.misc import format_date as odoo_format_date


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_template(self, template, values=None):
        """Ensure format_date helper is always available in QWeb report context.
        
        This fixes a KeyError: 'format_date' issue in Odoo 19 when rendering
        invoice PDFs during POS order processing where the helper was missing.
        """
        if values is None:
            values = {}
        if 'format_date' not in values:
            values['format_date'] = lambda date, date_format=False, lang_code=False: odoo_format_date(
                self.env, date, date_format=date_format, lang_code=lang_code
            )
        return super()._render_template(template, values)
