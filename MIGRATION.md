# isfehka 1.x → 2.0 — Migración a la arquitectura Opción B (`isfe_base`)

**Audiencia:** quien opere el upgrade de una base isfehka existente (PRODUCCIÓN
incluida). **Contrato:** retrocompatibilidad total — CUFEs, estados FE,
adjuntos PDF/XML, historial de chatter, contadores fiscales y enlaces de
compañía se preservan. La migración es por **RENAME/copias preservando ids**,
nunca por campos nuevos vacíos.

## Qué cambia

| Antes (1.x) | Después (2.0) | Mecanismo |
|---|---|---|
| `account_move.hka_status/cufe/qr/...` | `fe_status/fe_cufe/fe_qr/...` | `ALTER TABLE ... RENAME COLUMN` |
| `hka_pdf` / `hka_xml` (adjuntos) | `fe_pdf` / `fe_xml` | remap `ir_attachment.res_field` |
| historial chatter de `hka_status` | sigue visible bajo `fe_status` | remap `mail_tracking_value.field_id` |
| `isfehka.configuration` (modelo) | `isfe.configuration` (driver='hka') | copia SQL preservando `id` + contador |
| `res_company.hka_configuration_id` | `fe_configuration_id` | copia de valores (ids preservados) |
| `res_company.hka_branch_code/pos_code/auto_send` | `fe_*` | rename |
| `pos_config.hka_*` | `fe_*` | rename |
| `pos_payment_method.hka_payment_type` | `fe_payment_type` | **remapeo de VALORES** (catálogos distintos; el driver vuelve a mapear neutral→HKA al serializar) |
| grupos `isfehka.group_isfehka_user/manager` | `isfe_base.group_isfe_user/manager` | copia de membresías |
| catálogos geo (provincia/distrito/corregimiento) | mismos REGISTROS, xmlids adoptados por `isfe_base` | `pre_init_hook` de isfe_base |
| params `ir.config_parameter` `isfehka.*` (shape 18 legado) | fila `isfe.configuration` | copia + limpieza |

La tabla legada queda como `isfehka_configuration_legacy_bak` (artefacto de
rollback en la propia base); eliminarla es un paso manual post-verificación.

## Procedimiento (por base)

1. **Snapshot/backup completo de la BD** (obligatorio; es el rollback real).
2. Verificar que el ambiente NO emita en vivo durante la ventana (parar crons
   de facturación; POS cerrado idealmente).
3. Desplegar el código nuevo (`isfe_base` + `isfehka` 2.0) y ejecutar:
   `odoo -d <db> -u isfehka --stop-after-init`
   (Odoo instala `isfe_base` primero, luego corre `migrations/18.0.2.0.0/`).
4. La post-migración **falla en voz alta** (transacción abortada, BD intacta)
   si queda alguna columna `hka_*` en `account_move`, si alguna compañía queda
   apuntando a una configuración inexistente, o si algún contador fiscal quedó
   inválido.
5. Verificación manual (ver matriz abajo) antes de reabrir la operación.

## Rollback

- **Mecanismo principal: restaurar el snapshot del paso 1** y redeplegar el
  código 1.x. Los renames son reversibles en teoría, pero el camino soportado
  y ensayado es el snapshot.
- La copia de configuración es no destructiva hasta el final
  (`isfehka_configuration_legacy_bak` conserva los datos originales).
- No ejecutar emisiones entre upgrade y verificación: así el snapshot nunca
  pierde documentos fiscales.

## Matriz de pruebas (plan §2.4 — ejecutar antes de tocar producción)

| # | Caso | Cómo | Estado |
|---|---|---|---|
| a | Instalación limpia base+drivers (trio, multi-PAC) | Docker Odoo 18, `-i isfe_base,isfedfp,isfehka` + smokes | PASÓ 2026-06-11 (`tests/shell/`, isfe_base) |
| b | Upgrade de BD isfehka existente (shape 17: modelo configuración) | Docker: instalar isfehka 1.x, sembrar config/factura/adjuntos/método de pago, `-u isfehka`, verificar | PASÓ 2026-06-11 (`tests/shell/seed_legacy_a.py` + `verify_migration_a.py`) |
| b2 | Upgrade de BD isfehka existente (shape 18: params ICP) | ídem con seed por `ir.config_parameter` | PASÓ 2026-06-11 (`tests/shell/*_b.py`) |
| c | Emitir/anular/PDF/XML por tipo (01/04/06) | ambiente Pruebas del PAC (demo HKA), `test_mode=True` | pendiente (M6, requiere credenciales demo) |
| d | Integridad de datos (CUFE/QR/contadores/adjuntos/chatter) | asserts del seed-verify en (b)/(b2) + post-migración | PASÓ 2026-06-11 |
| e | Cumplimiento del payload por PAC contra el API real | M6 (cutover de ensayo, ambiente=02) | pendiente |
| f | Copia de una BD isfehka REAL (Inversora) antes del go-live | restaurar copia en staging, correr (b), verificar | pendiente (gate de M3→prod) |

## Notas de paridad / decisiones

- **Contadores (2026-06-12):** la base agrega `next_number_nc` (secuencia
  separada para NC/ND) y `pos_config_id` (contador por punto/caja) como
  columnas NUEVAS anulables. Los usuarios isfehka migrados quedan con ambas
  vacías = contador único compartido, comportamiento 1.x intacto (matriz (b)
  re-verificada 13/13 tras el cambio).
- **destinoOperacion (2026-06-12):** ahora se deriva del tipo de documento
  (exportación '03' → 2), no del país del cliente — el dato país demostró ser
  no confiable en producción (extranjeros con país=PA). Para receptores con
  país extranjero en ventas locales esto CORRIGE el destino respecto a 1.x.
- **Descuento fantasma de pricelist NO portado** (defecto, A Brand #629): el
  driver 2.0 emite `precioUnitario = price_unit` real y descuento solo desde
  `line.discount` y líneas de descuento explícitas.
- Líneas negativas de lealtad/cupones se reportan como descuentos
  (`listaDescBonificacion`), igual que 1.x — HKA rechaza precios negativos.
- El envío automático al confirmar se controla por
  `res.company.fe_auto_send_on_post` (antes `hka_auto_send_on_post`).
- 1.x enviaba en `_post()`; el base envía en `action_post()` (+ flujo POS
  explícito). Vigilar flujos automatizados que llamen `_post()` directo.
- El recibo POS con PDF de HKA (JS deshabilitado en 1.x/18 + `pos.hkapdf` +
  controladores `/pos/get_hka_pdf`) NO se portó: estaba muerto en 18. La tabla
  `pos_hkapdf` queda huérfana en BD (sin uso); limpiar manualmente si se desea.
- Los loaders POS estilo 17 (`_loader_params_*`) tampoco se portaron (API
  inexistente en 18); la edición de campos fiscales del cliente se hace en
  backend. Re-evaluar en el backport 17 si el POS necesita esos campos.
