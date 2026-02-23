import functools

from odoo import models


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def _render_template(self, template, values=None, *args, **kwargs):
        values = dict(values or {})
        self._isfehka_inject_qweb_helpers(values)
        return super()._render_template(template, values, *args, **kwargs)

    def _isfehka_inject_qweb_helpers(self, qcontext):
        env = self.env

        def _setdefault_helper(name, helper):
            qcontext.setdefault(name, functools.partial(helper, env))

        try:
            from odoo.tools.misc import format_date as _format_date

            _setdefault_helper("format_date", _format_date)
        except Exception:
            pass

        try:
            from odoo.tools.misc import format_datetime as _format_datetime

            _setdefault_helper("format_datetime", _format_datetime)
        except Exception:
            pass

        try:
            from odoo.tools.misc import formatLang as _formatLang

            _setdefault_helper("formatLang", _formatLang)
        except Exception:
            pass

