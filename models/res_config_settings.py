from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    """HKA credential extension of the neutral FE settings page.

    Follows the base's documented driver-extension contract (see
    ``isfe_base/models/res_config_settings.py``):

      * ``get_values``: call ``super()`` (the base resolves the company's active
        ``isfe.configuration`` and fills the neutral fields), then read the HKA
        credentials off ``company.fe_configuration_id``.
      * ``set_values``: call ``super()`` FIRST (the base selects/links the
        config and guarantees ``company.fe_configuration_id`` points at it),
        then write the HKA credentials onto that resolved config.

    Config creation: the base does NOT create credential-less configs. The
    driver owns credentials, so when none is selected but credentials are
    entered, it creates an ``isfe.configuration`` (driver='hka') and links the
    company here.

    The credential fields render on the single neutral FE Settings page via an
    xpath into the base's ``isfe_settings_extra`` anchor (see
    ``views/res_config_settings_views.xml``).
    """
    _inherit = 'res.config.settings'

    hka_token_empresa = fields.Char(string='HKA Token Empresa')
    hka_token_password = fields.Char(string='HKA Token Password')
    hka_wsdl_url = fields.Char(string='HKA WSDL URL')

    @api.model
    def get_values(self):
        res = super().get_values()
        company = self.company_id or self.env.company
        config = company.fe_configuration_id
        res.update(
            hka_token_empresa=config.hka_token_empresa if config else False,
            hka_token_password=config.hka_token_password if config else False,
            hka_wsdl_url=config.hka_wsdl_url if config else False,
        )
        return res

    def set_values(self):
        # super() (base) selects/links the config and guarantees
        # company.fe_configuration_id points at the active config.
        super().set_values()
        company = self.company_id or self.env.company
        config = company.fe_configuration_id
        if not config:
            # Driver owns credential-config creation: if the user entered any
            # credential but no config was selected, create and link one.
            if self.hka_token_empresa or self.hka_token_password or self.hka_wsdl_url:
                config = self.env['isfe.configuration'].create({
                    'name': 'HKA - %s' % (company.name or ''),
                    'company_id': company.id,
                    'driver': 'hka',
                    'test_mode': self.fe_test_mode,
                    'default_tipo_documento': self.fe_default_tipo_documento or '01',
                })
                company.write({'fe_configuration_id': config.id})
            else:
                return
        vals = {
            'hka_token_empresa': self.hka_token_empresa or False,
            'hka_token_password': self.hka_token_password or False,
            'hka_wsdl_url': self.hka_wsdl_url or False,
        }
        if not config.driver:
            # Saving HKA credentials marks the config as HKA-driven.
            vals['driver'] = 'hka'
        config.write(vals)
