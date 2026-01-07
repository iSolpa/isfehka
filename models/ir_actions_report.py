# -*- coding: utf-8 -*-
from odoo import models
from odoo.tools.misc import format_date as odoo_format_date, format_datetime as odoo_format_datetime


class IrActionsReport(models.Model):
    _inherit = 'ir.actions.report'

    def _render_template(self, template, data=None):
        """Ensure format_date and format_datetime helpers are always available in QWeb report context.
        
        This fixes KeyError issues in Odoo 19 when rendering invoice PDFs during
        POS order processing where these helpers were missing from context.
        """
        if data is None:
            data = {}
        if 'format_date' not in data:
            data['format_date'] = lambda date, date_format=False, lang_code=False: odoo_format_date(
                self.env, date, date_format=date_format, lang_code=lang_code
            )
        if 'format_datetime' not in data:
            data['format_datetime'] = lambda dt, tz=False, dt_format=False, lang_code=False: odoo_format_datetime(
                self.env, dt, tz=tz, dt_format=dt_format, lang_code=lang_code
            )
        return super()._render_template(template, data)

    def _render_qweb_html(self, report_ref, docids, data=None):
        """Override to ensure format_date and format_datetime are in the context before rendering."""
        if data is None:
            data = {}
        if 'format_date' not in data:
            data['format_date'] = lambda date, date_format=False, lang_code=False: odoo_format_date(
                self.env, date, date_format=date_format, lang_code=lang_code
            )
        if 'format_datetime' not in data:
            data['format_datetime'] = lambda dt, tz=False, dt_format=False, lang_code=False: odoo_format_datetime(
                self.env, dt, tz=tz, dt_format=dt_format, lang_code=lang_code
            )
        return super()._render_qweb_html(report_ref, docids, data)
