"""#2004: hka_fecha_recepcion_dgi held Panama wall-clock time in a UTC field.

On this branch every row was written that way, so all of them move +5 h. Verified on
A Brand production on 2026-11-06: 9,324 rows, each 5 to 7 h behind its document's
send time, none in UTC. pos.order keeps its copy untouched: the ticket prints it raw.

Undo: UPDATE account_move m SET hka_fecha_recepcion_dgi = b.hka_fecha_recepcion_dgi
      FROM _bak2004_account_move b WHERE b.id = m.id;
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute("""
        CREATE TABLE IF NOT EXISTS _bak2004_account_move AS
        SELECT id, hka_fecha_recepcion_dgi FROM account_move
        WHERE hka_fecha_recepcion_dgi IS NOT NULL
    """)
    cr.execute("""
        UPDATE account_move m
           SET hka_fecha_recepcion_dgi = b.hka_fecha_recepcion_dgi + INTERVAL '5 hours'
          FROM _bak2004_account_move b
         WHERE b.id = m.id AND m.hka_fecha_recepcion_dgi = b.hka_fecha_recepcion_dgi
    """)
