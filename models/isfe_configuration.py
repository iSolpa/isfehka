from odoo import models, fields, api


class IsfeConfiguration(models.Model):
    """HKA credential extension of the neutral FE configuration.

    Per the Option-B driver-extension pattern, the base ``isfe.configuration``
    holds only PAC-agnostic settings; this driver injects The Factory HKA's
    credentials via ``_inherit``.

    The M3 migration copies legacy ``isfehka.configuration`` rows into
    ``isfe.configuration`` preserving ids and the fiscal counter, mapping the
    legacy columns ``token_empresa`` / ``token_password`` / ``wsdl_url`` onto
    these ``hka_``-prefixed fields (namespaced so they can never collide with
    another PAC's credentials on a shared config table).
    """
    _inherit = 'isfe.configuration'

    driver = fields.Selection(
        selection_add=[('hka', 'The Factory HKA')],
        ondelete={'hka': 'set null'}
    )

    hka_token_empresa = fields.Char(
        string='HKA Token Empresa',
        copy=False,
        help='Token provisto por HKA para identificar la empresa.'
    )
    hka_token_password = fields.Char(
        string='HKA Token Password',
        copy=False,
        help='Contraseña asociada al token de la empresa en HKA.'
    )
    hka_wsdl_url = fields.Char(
        string='HKA WSDL URL',
        default=lambda self: self._default_hka_wsdl_url(),
        help='URL del servicio SOAP de HKA.'
    )

    @api.model
    def _default_hka_wsdl_url(self):
        return 'https://demoemision.thefactoryhka.com.pa/ws/obj/v1.0/Service.svc?singleWsdl'
