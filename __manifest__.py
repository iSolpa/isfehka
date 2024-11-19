{
    'name': 'Panama Electronic Invoicing - HKA Integration',
    'version': '1.0.1',
    'category': 'Accounting/Localizations',
    'summary': 'Electronic Invoicing Integration for Panama with HKA',
    'description': """
        Electronic Invoicing Integration for Panama
        =========================================
        
        This module provides integration with HKA's electronic invoicing system for Panama.
    """,
    'author': 'Independent Solutions',
    'website': 'https://www.isolpa.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'l10n_pa',
        'stock',
        'point_of_sale',
    ],
    'data': [
        'security/isfehka_security.xml',
        'security/ir.model.access.csv',
        'data/isfehka_data.xml',
        'data/res_country_state_data.xml',
        'data/res_location_pa_data.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/pos_config_views.xml',
        'report/account_move_report.xml',
        'report/account_move_templates.xml',
        'views/menu_views.xml',
    ],
    'external_dependencies': {
        'python': ['zeep'],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}