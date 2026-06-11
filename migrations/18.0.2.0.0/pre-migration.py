# -*- coding: utf-8 -*-
"""isfehka 1.x -> 2.0 (Option B): hka_* -> fe_* RENAME migration.

Runs while upgrading isfehka onto the isfe_base architecture. By the time this
script executes, isfe_base is already installed (new dependency, loaded first):
the neutral fe_* columns exist (EMPTY on legacy rows) and isfe_configuration
exists. This script moves the legacy data onto the neutral structures by
column RENAME / id-preserving copy — never by creating new fields — so CUFEs,
statuses, attachments, chatter tracking and fiscal counters survive intact.

Legacy shapes handled (both occur in the wild):
  * 17/main shape: model isfehka.configuration (+ res_company.hka_configuration_id)
  * legacy-18 shape: ir.config_parameter isfehka.* globals

Everything is guarded by column/table existence checks -> idempotent and safe
to re-run on a restored snapshot.

Rollback: restore the pre-upgrade database snapshot (see MIGRATION.md; the
legacy config table is also kept as isfehka_configuration_legacy_bak).
"""
import logging

_logger = logging.getLogger(__name__)


def table_exists(cr, table):
    cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = %s", [table])
    return bool(cr.fetchone())


def column_exists(cr, table, column):
    cr.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, [table, column])
    return bool(cr.fetchone())


def rename_column(cr, table, old, new):
    """Rename ``old`` -> ``new``, absorbing the ``new`` column isfe_base just
    created. The LEGACY column is authoritative: when ``new`` already exists
    it may carry ORM-backfilled DEFAULTS on every legacy row (e.g. fe_status
    'draft', fe_branch_code '0000' — written at base install), so the copy
    must overwrite unconditionally, never fill-gaps-only."""
    if not column_exists(cr, table, old):
        return
    if column_exists(cr, table, new):
        cr.execute(f'SELECT 1 FROM "{table}" WHERE "{new}" IS NOT NULL LIMIT 1')
        if cr.fetchone():
            _logger.info('isfehka migr: %s.%s pre-filled (ORM defaults); '
                         'overwriting from legacy %s', table, new, old)
            cr.execute(f'UPDATE "{table}" SET "{new}" = "{old}"')
            cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{old}"')
            return
        cr.execute(f'ALTER TABLE "{table}" DROP COLUMN "{new}"')
    cr.execute(f'ALTER TABLE "{table}" RENAME COLUMN "{old}" TO "{new}"')
    _logger.info('isfehka migr: renamed %s.%s -> %s', table, old, new)


def migrate(cr, version):
    _logger.info('isfehka 2.0 pre-migration starting (from version %s)', version)

    # ------------------------------------------------------------------
    # 0. Insurance: deactivate legacy isfehka views (normally already done
    #    by isfe_base's pre_init_hook).
    # ------------------------------------------------------------------
    cr.execute("""
        UPDATE ir_ui_view SET active = false
         WHERE id IN (SELECT res_id FROM ir_model_data
                       WHERE module = 'isfehka' AND model = 'ir.ui.view')
    """)

    # ------------------------------------------------------------------
    # 1. Preserve chatter tracking history of the FE status BEFORE any
    #    field-metadata cleanup (mail_tracking_value cascades on field_id).
    # ------------------------------------------------------------------
    if table_exists(cr, 'mail_tracking_value'):
        cr.execute("""
            UPDATE mail_tracking_value mtv
               SET field_id = fnew.id
              FROM ir_model_fields fold, ir_model_fields fnew
             WHERE fold.model = 'account.move' AND fold.name = 'hka_status'
               AND fnew.model = 'account.move' AND fnew.name = 'fe_status'
               AND mtv.field_id = fold.id
        """)
        _logger.info('isfehka migr: remapped %s hka_status tracking values', cr.rowcount)

    # ------------------------------------------------------------------
    # 2. account.move: hka_* -> fe_* column renames + attachment remap.
    # ------------------------------------------------------------------
    for old, new in [
        ('hka_status', 'fe_status'),
        ('hka_cufe', 'fe_cufe'),
        ('hka_qr', 'fe_qr'),
        ('hka_nro_protocolo_autorizacion', 'fe_nro_protocolo_autorizacion'),
        ('hka_fecha_recepcion_dgi', 'fe_fecha_recepcion_dgi'),
        ('hka_pdf_filename', 'fe_pdf_filename'),
        ('hka_xml_filename', 'fe_xml_filename'),
        ('hka_message', 'fe_message'),
    ]:
        rename_column(cr, 'account_move', old, new)

    # hka_pdf / hka_xml are attachment-backed binaries: the data lives in
    # ir_attachment rows keyed by res_field, not in account_move columns.
    cr.execute("""
        UPDATE ir_attachment SET res_field = 'fe_pdf'
         WHERE res_model = 'account.move' AND res_field = 'hka_pdf'
    """)
    cr.execute("""
        UPDATE ir_attachment SET res_field = 'fe_xml'
         WHERE res_model = 'account.move' AND res_field = 'hka_xml'
    """)

    # ------------------------------------------------------------------
    # 3. res.company / pos.config scalar renames.
    # ------------------------------------------------------------------
    for old, new in [
        ('hka_branch_code', 'fe_branch_code'),
        ('hka_pos_code', 'fe_pos_code'),
        ('hka_auto_send_on_post', 'fe_auto_send_on_post'),  # 17/main shape only
    ]:
        rename_column(cr, 'res_company', old, new)

    for old, new in [
        ('hka_pos_code', 'fe_pos_code'),
        ('use_hka_pdf_receipt', 'use_fe_pdf_receipt'),
        ('hka_tipo_documento', 'fe_tipo_documento'),
        ('hka_naturaleza_operacion', 'fe_naturaleza_operacion'),
    ]:
        rename_column(cr, 'pos_config', old, new)

    # ------------------------------------------------------------------
    # 4. pos.payment.method: hka_payment_type -> fe_payment_type is a VALUE
    #    remap, not a rename — the catalogs differ (HKA formaPagoFact codes
    #    vs the neutral DGI-style catalog the base defines; the driver maps
    #    neutral -> HKA at serialization).
    # ------------------------------------------------------------------
    if column_exists(cr, 'pos_payment_method', 'hka_payment_type'):
        cr.execute("""
            UPDATE pos_payment_method SET fe_payment_type = CASE hka_payment_type
                WHEN '01' THEN '09'  -- Crédito            -> Crédito del establecimiento
                WHEN '02' THEN '01'  -- Efectivo           -> Efectivo
                WHEN '03' THEN '03'  -- Tarjeta Crédito    -> Tarjeta de Crédito
                WHEN '04' THEN '04'  -- Tarjeta Débito     -> Tarjeta de Débito
                WHEN '05' THEN '08'  -- Tarj. Fidelización -> Puntos de Fidelización
                WHEN '06' THEN '07'  -- Vale               -> Bonos/Cert. de Regalo
                WHEN '07' THEN '07'  -- Tarjeta de Regalo  -> Bonos/Cert. de Regalo
                WHEN '08' THEN '05'  -- Transf/Depósito    -> Transferencia
                WHEN '09' THEN '02'  -- Cheque             -> Cheque
                ELSE '99'
            END
            WHERE hka_payment_type IS NOT NULL
        """)
        cr.execute('ALTER TABLE pos_payment_method DROP COLUMN hka_payment_type')
        _logger.info('isfehka migr: remapped pos payment method codes')

    # ------------------------------------------------------------------
    # 5. Configuration: isfehka.configuration -> isfe.configuration.
    # ------------------------------------------------------------------
    if table_exists(cr, 'isfehka_configuration'):
        # The driver's credential columns are created by the ORM only AFTER
        # this script; pre-create them so the copy is one shot.
        for col in ('hka_token_empresa', 'hka_token_password', 'hka_wsdl_url'):
            if not column_exists(cr, 'isfe_configuration', col):
                cr.execute(f'ALTER TABLE isfe_configuration ADD COLUMN "{col}" varchar')

        cr.execute("""
            INSERT INTO isfe_configuration
                   (id, name, active, test_mode, default_tipo_documento,
                    next_number, driver,
                    hka_token_empresa, hka_token_password, hka_wsdl_url,
                    create_uid, create_date, write_uid, write_date)
            SELECT id, name, active, test_mode, default_tipo_documento,
                   next_number, 'hka',
                   token_empresa, token_password, wsdl_url,
                   create_uid, create_date, write_uid, write_date
              FROM isfehka_configuration
                ON CONFLICT (id) DO NOTHING
        """)
        copied = cr.rowcount
        cr.execute("""
            SELECT setval(pg_get_serial_sequence('isfe_configuration', 'id'),
                          GREATEST((SELECT COALESCE(MAX(id), 1) FROM isfe_configuration), 1))
        """)
        _logger.info('isfehka migr: copied %s configuration rows (ids preserved)', copied)

        # Company -> configuration link (ids preserved, so a value copy is
        # FK-safe against the new table).
        if column_exists(cr, 'res_company', 'hka_configuration_id'):
            cr.execute("""
                UPDATE res_company SET fe_configuration_id = hka_configuration_id
                 WHERE hka_configuration_id IS NOT NULL
                   AND fe_configuration_id IS NULL
            """)
            cr.execute('ALTER TABLE res_company DROP COLUMN hka_configuration_id')

        # Multi-company ownership (per the config-multicompany decision):
        # a config serving exactly ONE company belongs to it; one serving
        # several stays global (company_id NULL).
        cr.execute("""
            UPDATE isfe_configuration c
               SET company_id = sub.company_id
              FROM (SELECT fe_configuration_id AS conf_id,
                           MIN(id) AS company_id, COUNT(*) AS n
                      FROM res_company
                     WHERE fe_configuration_id IS NOT NULL
                     GROUP BY fe_configuration_id) sub
             WHERE sub.conf_id = c.id AND sub.n = 1 AND c.company_id IS NULL
        """)

        # Keep the legacy table as an in-database rollback artifact; dropping
        # it is a manual post-verification step (see MIGRATION.md).
        cr.execute('ALTER TABLE isfehka_configuration RENAME TO isfehka_configuration_legacy_bak')

    else:
        # Legacy-18 shape: globals on ir.config_parameter.
        cr.execute("SELECT key, value FROM ir_config_parameter WHERE key LIKE 'isfehka.%%'")
        params = dict(cr.fetchall())
        if params.get('isfehka.token_empresa') or params.get('isfehka.wsdl_url'):
            for col in ('hka_token_empresa', 'hka_token_password', 'hka_wsdl_url'):
                if not column_exists(cr, 'isfe_configuration', col):
                    cr.execute(f'ALTER TABLE isfe_configuration ADD COLUMN "{col}" varchar')
            cr.execute("""
                INSERT INTO isfe_configuration
                       (name, active, test_mode, default_tipo_documento,
                        next_number, driver,
                        hka_token_empresa, hka_token_password, hka_wsdl_url,
                        create_date, write_date)
                VALUES ('HKA (migrada)', true, %s, %s, %s, 'hka', %s, %s, %s,
                        now() at time zone 'UTC', now() at time zone 'UTC')
                RETURNING id
            """, [
                (params.get('isfehka.test_mode') or '').strip().lower() in ('true', '1'),
                params.get('isfehka.default_tipo_documento') or '01',
                (params.get('isfehka.next_number') or '0000000001').zfill(10),
                params.get('isfehka.token_empresa'),
                params.get('isfehka.token_password'),
                params.get('isfehka.wsdl_url'),
            ])
            config_id = cr.fetchone()[0]
            # The ICP shape was a database-wide global: link every company
            # that has no config yet; the config itself stays shared
            # (company_id NULL).
            cr.execute("""
                UPDATE res_company SET fe_configuration_id = %s
                 WHERE fe_configuration_id IS NULL
            """, [config_id])
            _logger.info('isfehka migr: migrated ICP globals into isfe_configuration %s',
                         config_id)

    # Legacy ICP globals are obsolete in BOTH shapes (the table shape may
    # carry stale isfehka.* params from the old settings page as well).
    cr.execute("DELETE FROM ir_config_parameter WHERE key LIKE 'isfehka.%%'")

    # ------------------------------------------------------------------
    # 6. Group memberships: legacy HKA groups -> neutral FE groups.
    #    (The legacy groups themselves are auto-removed at the end of the
    #    upgrade since the module no longer ships them.)
    # ------------------------------------------------------------------
    for legacy_xml, base_xml in [
        ('group_isfehka_user', 'group_isfe_user'),
        ('group_isfehka_manager', 'group_isfe_manager'),
    ]:
        cr.execute("""
            INSERT INTO res_groups_users_rel (gid, uid)
            SELECT b.res_id, rel.uid
              FROM ir_model_data l
              JOIN res_groups_users_rel rel ON rel.gid = l.res_id
              JOIN ir_model_data b
                ON b.module = 'isfe_base' AND b.name = %s AND b.model = 'res.groups'
             WHERE l.module = 'isfehka' AND l.name = %s AND l.model = 'res.groups'
                ON CONFLICT DO NOTHING
        """, [base_xml, legacy_xml])

    # ------------------------------------------------------------------
    # 7. xmlid ownership cleanup, so the end-of-upgrade orphan sweep does
    #    not delete live records/metadata:
    #    - geo/state records now belong to isfe_base (adopted by its
    #      pre_init_hook) -> drop the legacy pointers to keep the rows.
    #    - model/field/access metadata that isfe_base now also owns (same
    #      deterministic names: the account.move FE fields kept by the base,
    #      the cancel wizard, partner fields...) -> drop the legacy
    #      duplicates so the shared ir.model.fields rows are not swept.
    # ------------------------------------------------------------------
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'isfehka'
           AND model IN ('res.country.state', 'res.distrito.pa', 'res.corregimiento.pa')
    """)
    cr.execute("""
        DELETE FROM ir_model_data a
         WHERE a.module = 'isfehka'
           AND a.model IN ('ir.model', 'ir.model.fields',
                           'ir.model.constraint', 'ir.model.relation')
           AND EXISTS (SELECT 1 FROM ir_model_data b
                        WHERE b.module = 'isfe_base'
                          AND b.name = a.name AND b.model = a.model)
    """)
    # Legacy ACLs are obsolete (the base ships its own and the new driver has
    # none): delete the RECORDS, not just their xmlids — a de-referenced ACL
    # row would keep an FK onto the legacy groups and break the
    # end-of-upgrade sweep that removes those groups.
    cr.execute("""
        DELETE FROM ir_model_access a
         USING ir_model_data d
         WHERE d.module = 'isfehka' AND d.model = 'ir.model.access'
           AND d.res_id = a.id
    """)
    cr.execute("DELETE FROM ir_model_data WHERE module = 'isfehka' AND model = 'ir.model.access'")
    _logger.info('isfehka 2.0 pre-migration done')
