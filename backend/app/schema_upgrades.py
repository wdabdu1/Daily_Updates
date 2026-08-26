"""Forward-compatible, non-destructive schema patches for columns whose
CONSTRAINT changed on an existing table -- create_all() only creates missing
tables/columns, it never alters an existing column (same reason
migrate_legacy.py has to hand-patch users.created_at). Unlike the legacy
migration, these patches apply regardless of whether old-app tables were
ever present, since they fix up the CURRENT schema, not a migration from the
old one -- so this runs on every startup, unconditionally.

Keep every patch here naturally idempotent (DROP NOT NULL, ADD COLUMN IF NOT
EXISTS, etc.) so re-running it on every restart is always safe, rather than
introducing a migrations-version table for a small number of patches.
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("schema_upgrades")


def apply_schema_upgrades(engine: Engine) -> list[str]:
    report: list[str] = []

    # SQLite (local dev) always gets a fresh create_all() from the current
    # models.py, so its columns are already correct -- these ALTER
    # statements are Postgres syntax and Postgres-only in practice.
    if engine.dialect.name != "postgresql":
        return report

    inspector = inspect(engine)
    if "master_accounts" not in inspector.get_table_names():
        return report

    cols = {c["name"]: c for c in inspector.get_columns("master_accounts")}
    to_relax = [
        name
        for name in ("business_unit_id", "division_id")
        if name in cols and not cols[name]["nullable"]
    ]
    if to_relax:
        with engine.begin() as conn:
            for col in to_relax:
                conn.execute(text(f"ALTER TABLE master_accounts ALTER COLUMN {col} DROP NOT NULL"))
        report.append(
            f"Relaxed NOT NULL on master_accounts({', '.join(to_relax)}) -- Bank Dues"
            " accounts can now be created without a known Business Unit/Division."
        )

    # Widen numeric columns that started out narrower than models.py's
    # current declaration now needs. This is the same class of drift as the
    # NOT NULL patch above: `amount = Column(Numeric(15, 2))` was bumped to
    # Numeric(20, 2) in models.py, but that change alone never reaches an
    # already-existing Postgres table -- the column stayed at its original,
    # narrower precision (traced to a real incident: SDG amounts in the
    # hundreds of millions overflowed a `numeric(10, 2)` bank_dues.amount
    # column on the live table with a bare "Internal Server Error", which
    # a fresh local Postgres instance -- created via create_all() from the
    # current models.py -- could not reproduce). Only ever widen (never
    # narrow -- that could truncate real data), so this is safe to run
    # unconditionally on every startup.
    NUMERIC_WIDENING_TARGETS = [
        # (table, column, target_precision, target_scale)
        ("bank_dues", "amount", 20, 2),
        ("receivables_daily", "amount", 20, 2),
    ]
    for table, column, target_precision, target_scale in NUMERIC_WIDENING_TARGETS:
        if table not in inspector.get_table_names():
            continue
        col_info = {c["name"]: c for c in inspector.get_columns(table)}.get(column)
        if not col_info:
            continue
        col_type = col_info["type"]
        current_precision = getattr(col_type, "precision", None)
        current_scale = getattr(col_type, "scale", None)
        if current_precision is None:
            continue  # not a NUMERIC column (or dialect didn't report it) -- leave alone
        if current_precision >= target_precision and (current_scale or 0) >= target_scale:
            continue  # already at least as wide as we need
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"ALTER TABLE {table} ALTER COLUMN {column} TYPE"
                    f" numeric({target_precision}, {target_scale})"
                )
            )
        report.append(
            f"Widened {table}.{column} from numeric({current_precision}, {current_scale}) to"
            f" numeric({target_precision}, {target_scale}) -- large amounts no longer overflow it."
        )

    return report
