from odoo import models

class PosSession(models.Model):
    _inherit = 'pos.session'

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        result.append('pos.hkapdf')
        return result

    def _loader_params_pos_hkapdf(self):
        return {
            'search_params': {
                'domain': [],
                'fields': ['name', 'image_data'],
            },
        }

    def _get_pos_ui_pos_hkapdf(self, params):
        return self.env['pos.hkapdf'].search_read(**params['search_params'])
