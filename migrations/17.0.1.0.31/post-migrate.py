def migrate(cr, version):
    # Existing Extranjero contacts were never asked for an ID type; declaring them all
    # Pasaporte (the field default) would be false for national IDs. Mark them Otro ('99'),
    # which is what the module always sent before; new contacts still default to Pasaporte.
    if not version:
        return
    cr.execute("UPDATE res_partner SET tipo_identificacion = '99' WHERE tipo_cliente_fe = '04'")
