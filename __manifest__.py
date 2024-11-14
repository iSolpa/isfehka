{
    'name': 'Panama Electronic Invoicing - HKA Integration',
    'version': '1.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Electronic Invoicing Integration for Panama with HKA',
    'description': """
        Electronic Invoicing Integration for Panama
        =========================================
        
        This module provides integration with HKA's electronic invoicing system for Panama.
        
        Features:
        - RUC verification and validation
        - Electronic invoice generation and submission
        - Support for all fiscal document types
        - Document cancellation
        - Integration with inventory management
        - Multi-language support (English/Spanish)
    """,
    'author': 'Independent Solutions',
    'website': 'https://www.isolpa.com',
    'license': 'OPL-1',
    'depends': [
        'base',
        'account',
        'l10n_pa',
        'stock',
        'base_setup',
    ],
    'data': [
        'security/isfehka_security.xml',
        'security/ir.model.access.csv',
        'data/isfehka_data.xml',
        'report/account_move_report.xml',
        'report/account_move_templates.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
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