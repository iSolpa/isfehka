from odoo import models
import logging

_logger = logging.getLogger(__name__)

class PosSession(models.Model):
    _inherit = 'pos.session'

    def _get_pos_ui_pos_hkapdf(self, params):
        return self.env['pos.hkapdf'].search_read(**params['search_params'])

    def _pos_data_process(self, loaded_data):
        result = super()._pos_data_process(loaded_data)
        if 'res.partner' in loaded_data:
            _logger.info("[ISFEHKA] Processing partners in _pos_data_process")
            for partner in loaded_data['res.partner']:
                if 'ruc' not in partner:
                    partner['ruc'] = False
        return result

    def _loader_params_res_partner(self):
        result = super()._loader_params_res_partner()
        _logger.info("[ISFEHKA] _loader_params_res_partner before: %s", result)
        new_fields = ['ruc', 'dv', 'tipo_contribuyente', 'tipo_cliente_fe',
                     'l10n_pa_distrito_id', 'l10n_pa_corregimiento_id',
                     'ruc_verified', 'ruc_verification_date']
        for field in new_fields:
            if field not in result['search_params']['fields']:
                result['search_params']['fields'].append(field)
        _logger.info("[ISFEHKA] _loader_params_res_partner after: %s", result)
        return result

    def _get_pos_ui_res_partner(self, params):
        _logger.info("[ISFEHKA] _get_pos_ui_res_partner params: %s", params)
        result = super()._get_pos_ui_res_partner(params)
        _logger.info("[ISFEHKA] _get_pos_ui_res_partner result: %s", result)
        return result

    def update_partner_from_ui(self, partner):
        _logger.info("[ISFEHKA] Updating partner from UI with data: %s", partner)
        result = super().update_partner_from_ui(partner)
        _logger.info("[ISFEHKA] Partner update result: %s", result)
        return result

    def get_pos_ui_res_partner_by_params(self, params):
        _logger.info("[ISFEHKA] get_pos_ui_res_partner_by_params params: %s", params)
        fields_to_read = [
            'name', 'street', 'city', 'state_id', 'country_id', 'vat', 'lang',
            'phone', 'zip', 'mobile', 'email', 'barcode', 'write_date',
            'property_account_position_id', 'property_product_pricelist', 'parent_name',
            'ruc', 'dv', 'tipo_contribuyente', 'tipo_cliente_fe',
            'l10n_pa_distrito_id', 'l10n_pa_corregimiento_id',
            'ruc_verified', 'ruc_verification_date'
        ]
        params['fields'] = fields_to_read
        result = self.env['res.partner'].search_read(**params)
        _logger.info("[ISFEHKA] get_pos_ui_res_partner_by_params result length: %s", len(result))
        return result

    def _pos_ui_models_to_load(self):
        result = super()._pos_ui_models_to_load()
        if 'res.distrito.pa' not in result:
            result.append('res.distrito.pa')
        if 'res.corregimiento.pa' not in result:
            result.append('res.corregimiento.pa')
        return result

    def _loader_params_res_distrito_pa(self):
        _logger.info("[ISFEHKA] Loading distrito params")
        return {
            'search_params': {
                'fields': ['name', 'code', 'state_id'],
                'domain': [],
                'order': 'name asc',
            },
        }

    def _loader_params_res_corregimiento_pa(self):
        return {
            'search_params': {
                'fields': ['name', 'code', 'distrito_id'],
                'domain': [],
                'order': 'name asc',
            },
        }

    def _get_pos_ui_res_distrito_pa(self, params):
        _logger.info("[ISFEHKA] Getting distrito data")
        return self.env['res.distrito.pa'].search_read(**params['search_params'])

    def _get_pos_ui_res_corregimiento_pa(self, params):
        return self.env['res.corregimiento.pa'].search_read(**params['search_params'])
