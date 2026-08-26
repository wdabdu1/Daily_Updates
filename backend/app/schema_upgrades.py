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

    # Fix a second-order effect of the legacy `master_accounts` rename in
    # migrate_legacy.py: `prepare_legacy_rename()` renames the OLD
    # `master_accounts` table to `master_accounts_legacy` *before*
    # `create_all()` builds a brand-new `master_accounts` table under the
    # now-freed name. Postgres foreign keys track the referenced table by
    # its internal identity, not by name -- so any FK that already existed
    # on another table from the original legacy app (e.g. the legacy app's
    # own `bank_dues.account_id -> master_accounts.id` constraint) follows
    # the rename and keeps pointing at the OLD table under its new name,
    # never at the new live `master_accounts` table this app actually
    # writes accounts into going forward. A due/receivable on any account
    # created *after* the migration ran (a fresh id that only ever existed
    # in the new table) then fails with a foreign key violation reported
    # against `master_accounts_legacy` -- confirmed against a real
    # production error (`account_id=3 is not present in table
    # "master_accounts_legacy"` on a genuinely valid, existing account).
    # Only re-point a constraint that is actually misdirected (never touch
    # one already correctly pointing at `master_accounts`). Safe to do here
    # -- this runs after run_legacy_migration() above, by which point every
    # legacy master_accounts row has already been copied into the new
    # table with the same id, so no existing bank_dues/receivables_daily
    # row can violate the corrected constraint.
    ACCOUNT_FK_TARGETS = [
        ("bank_dues", "account_id", "CASCADE"),
        ("receivables_daily", "account_id", "CASCADE"),
    ]
    for table, column, ondelete in ACCOUNT_FK_TARGETS:
        if table not in inspector.get_table_names():
            continue
        for fk in inspector.get_foreign_keys(table):
            if fk.get("constrained_columns") != [column]:
                continue
            referred_table = fk.get("referred_table")
            if referred_table == "master_accounts":
                continue  # already correct
            constraint_name = fk.get("name") or f"{table}_{column}_fkey"
            with engine.begin() as conn:
                if fk.get("name"):
                    conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {fk['name']}"))
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD CONSTRAINT {constraint_name}"
                        f" FOREIGN KEY ({column}) REFERENCES master_accounts (id)"
                        f" ON DELETE {ondelete}"
                    )
                )
            report.append(
                f"Re-pointed {table}.{column}'s foreign key from '{referred_table}' to"
                " 'master_accounts' -- it was still targeting the renamed legacy table"
                " after migration, which rejected any due/receivable on an account"
                " created after the migration ran."
            )

    # Round 12: users.display_name / users.email are new columns on an
    # existing table -- create_all() never adds a column to a table that
    # already exists in production, same reasoning as every patch above.
    # ADD COLUMN IF NOT EXISTS is naturally idempotent, so this can run
    # unconditionally on every startup with no existence check needed.
    if "users" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        added = []
        with engine.begin() as conn:
            if "display_name" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name VARCHAR(150)"))
                added.append("display_name")
            if "email" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(255)"))
                added.append("email")
        if added:
            report.append(f"Added users({', '.join(added)}) -- new optional profile columns.")

    return report
