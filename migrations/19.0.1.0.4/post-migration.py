from odoo import tools


def migrate(cr, version):
    """
    Add hka_payment_type column to account_payment_method_line table if it doesn't exist.
    This migration ensures the field is properly created in Odoo 19.
    """
    if tools.column_exists(cr, 'account_payment_method_line', 'hka_payment_type'):
        return
    
    # Execute the SQL script to add the column
    with open(__file__.replace('post-migration.py', 'add_hka_payment_type.sql'), 'r') as f:
        cr.execute(f.read())
