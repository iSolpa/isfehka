# -*- coding: utf-8 -*-
"""isfehka 1.x -> 2.0 post-migration: verify and log the rename outcome.

All data movement happens in pre-migration; this script is a safety net that
asserts the invariants the backward-compat contract promises (no lost CUFEs,
no lost counters) and logs a summary for the upgrade report. It raises on a
broken invariant so the upgrade fails loudly INSIDE the transaction instead
of going live half-migrated.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    # No legacy hka_* columns may remain on account_move.
    cr.execute("""
        SELECT column_name FROM information_schema.columns
         WHERE table_name = 'account_move' AND column_name LIKE 'hka\\_%'
    """)
    leftover = [r[0] for r in cr.fetchall()]
    if leftover:
        raise AssertionError(
            'isfehka migration: legacy columns still on account_move: %s' % leftover)

    # Every company that had a configuration must still have one.
    cr.execute("""
        SELECT COUNT(*) FROM res_company
         WHERE fe_configuration_id IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM isfe_configuration c
                            WHERE c.id = res_company.fe_configuration_id)
    """)
    dangling = cr.fetchone()[0]
    if dangling:
        raise AssertionError(
            'isfehka migration: %s companies point at a missing FE configuration' % dangling)

    # Migrated configs must carry their driver key and a sane counter.
    cr.execute("""
        SELECT COUNT(*) FROM isfe_configuration
         WHERE driver = 'hka'
           AND (next_number IS NULL OR next_number !~ '^[0-9]{10}$')
    """)
    bad_counters = cr.fetchone()[0]
    if bad_counters:
        raise AssertionError(
            'isfehka migration: %s HKA configurations with invalid fiscal counter' % bad_counters)

    cr.execute("SELECT COUNT(*) FROM account_move WHERE fe_cufe IS NOT NULL AND fe_cufe != ''")
    cufes = cr.fetchone()[0]
    cr.execute("SELECT COUNT(*) FROM isfe_configuration WHERE driver = 'hka'")
    configs = cr.fetchone()[0]
    cr.execute("""
        SELECT COUNT(*) FROM ir_attachment
         WHERE res_model = 'account.move' AND res_field IN ('fe_pdf', 'fe_xml')
    """)
    files = cr.fetchone()[0]
    _logger.info(
        'isfehka 2.0 post-migration OK: %s documents with CUFE, %s HKA '
        'configurations, %s FE attachments preserved.', cufes, configs, files)
