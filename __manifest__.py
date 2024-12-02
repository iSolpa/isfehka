{
    'name': 'Panama Electronic Invoicing - HKA Integration',
    'version': '1.0.4',
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
        'custom_receipts_for_pos',
    ],
    'data': [
        'security/isfehka_security.xml',
        'security/ir.model.access.csv',
        'data/isfehka_data.xml',
        'data/res_country_state_data.xml',
        'data/res_location_pa_data.xml',
        'wizard/account_move_cancel_reason_views.xml',
        'views/res_company_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/account_move_views.xml',
        'views/pos_config_views.xml',
        'report/account_move_report.xml',
        'report/account_move_templates.xml',
        'views/menu_views.xml',
    ],
    'assets': {
        'point_of_sale._assets_pos': [
            ('prepend', 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js'),
            ('prepend', 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js'),
            'isfehka/static/src/js/pos_order_receipt.js',
        ],
    },
    'external_dependencies': {
        'python': ['zeep'],
    },
    'images': ['static/description/icon.png'],
    'installable': True,
    'application': True,
    'auto_install': False,
}