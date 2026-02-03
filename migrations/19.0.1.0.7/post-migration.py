def migrate(cr, version):
    """
    Fix hka_fecha_recepcion_dgi timezone issue.
    
    The field was stored incorrectly: HKA returns datetime in Panama time (-05:00),
    but it was stored as-is without converting to UTC. This migration adds 5 hours
    to all existing records to correct the stored values.
    
    This runs only on upgrade, not on fresh install.
    """
    if not version:
        # Fresh install, no migration needed
        return
    
    # Add 5 hours to all existing hka_fecha_recepcion_dgi values
    # Using INTERVAL to add 5 hours in PostgreSQL
    cr.execute("""
        UPDATE account_move
        SET hka_fecha_recepcion_dgi = hka_fecha_recepcion_dgi + INTERVAL '5 hours'
        WHERE hka_fecha_recepcion_dgi IS NOT NULL;
    """)
