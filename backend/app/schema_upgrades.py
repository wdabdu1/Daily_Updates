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

    return report
