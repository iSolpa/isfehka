# Harness de la migración 1.x -> 2.0 (matriz (b)/(b2) de MIGRATION.md)

Vía `odoo shell` contra Docker desechable (ver isfe_base/tests/shell/README.md
para el setup). Ciclo:

1. Instalar isfehka 1.x (worktree de la rama vieja) en BD fresca.
2. `seed_legacy_a.py` (shape 17: tabla isfehka_configuration) o
   `seed_legacy_b.py` (shape 18 legado: params ICP).
3. Upgrade con el código nuevo: `-u isfehka --stop-after-init`.
4. `verify_migration_a.py` / `verify_migration_b.py` — asserts de
   retrocompatibilidad (CUFE/estado/adjuntos/contadores/grupos/geo/dispatch).

Nota: usar un volumen para /var/lib/odoo entre pasos (los adjuntos viven en el
filestore, no en la BD).
