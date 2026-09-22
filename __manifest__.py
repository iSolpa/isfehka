{
    'name': 'Panama Electronic Invoicing - HKA Driver',
    'version': '18.0.2.0.2',
    'category': 'Accounting/Localizations',
    'summary': 'The Factory HKA PAC driver for Panama electronic invoicing (isfe_base)',
    'description': """
        Electronic Invoicing for Panama - The Factory HKA driver
        =========================================================

        Thin PAC driver on top of ``isfe_base`` (the neutral Panama FE layer).
        This module contains ONLY what is HKA-specific:

        * ``isfe.driver.hka``: serialization of the neutral FE document to
          HKA's SOAP payload, submission/cancellation/document retrieval via
          zeep, RUC verification (ConsultarRucDV).
        * HKA credentials on ``isfe.configuration`` (driver-extension fields)
          and their settings surface.

        Everything else (FE fields on account.move, POS flow, partner fiscal
        data, geo catalogs, views, security) lives in ``isfe_base``.

        Upgrading from isfehka <= 1.x runs the bundled migration that renames
        the legacy ``hka_*`` columns / ``isfehka.configuration`` data onto the
        neutral ``fe_*`` / ``isfe.configuration`` structures, preserving CUFEs,
        statuses, attachments and fiscal counters.
    """,
    'author': 'Independent Solutions',
    'website': 'https://www.isolpa.com',
    'license': 'OPL-1',
    'depends': [
        'isfe_base',
    ],
    'data': [
        'data/isfehka_data.xml',
        'views/res_config_settings_views.xml',
    ],
    'external_dependencies': {
        'python': ['zeep'],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
