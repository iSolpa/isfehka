from odoo import tools, api


def migrate(cr, version):
    """
    Pre-migration script to handle hka_payment_type field setup for Odoo 19.
    This ensures the field is properly prepared before the main migration.
    """
    # Check if the column already exists
    if tools.column_exists(cr, 'account_payment_method_line', 'hka_payment_type'):
        # Column exists, no action needed in pre-migration
        return
    
    # The column doesn't exist, will be created in post-migration
    # This is expected for fresh installations or upgrades from versions without this field
    pass
