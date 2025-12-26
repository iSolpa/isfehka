def migrate(cr, version):
    """
    Add hka_payment_type column to account_payment_method_line table if it doesn't exist.
    This migration ensures the field is properly created in Odoo 19.
    """
    # Check if the column already exists using SQL query
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'account_payment_method_line' 
        AND column_name = 'hka_payment_type';
    """)
    
    if cr.fetchone():
        return
    
    # Execute the SQL script to add the column
    with open(__file__.replace('post-migration.py', 'add_hka_payment_type.sql'), 'r') as f:
        cr.execute(f.read())
