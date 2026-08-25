"""One-time, idempotent migration from the old single-file Streamlit app's
schema into the new schema, run automatically on startup (see main.py).

Design goals:
  - Never destroy old data. Where the old and new schema disagree on the
    shape of a table with the same name, the old table is renamed to
    "<name>_legacy" rather than dropped, so nothing is lost even if this
    script has a bug.
  - Safe to run on a totally empty database too -- in that case there is
    nothing to detect and this becomes a no-op, and normal seeding
    (see seed.py) takes over.
  - Safe to run more than once -- guarded by checking whether the legacy
    tables still exist / still have unmigrated shape.

Old schema (from gemini-code-*.py):
  users(id, username, password_hash[sha256 hex, 64 chars], role)
  bus(id, name)
  banks(id, short_name, full_name)
  currencies(code)
  master_accounts(id, bu, department, bank_shortname, bank_name,
                   account_number, account_name, currency)
  exchange_rates(id, rate_date, currency_pair, rate, is_auto_filled)
  bank_dues(id, account_id, due_date, facility_type, amount, status)
  daily_cash_positions(id, position_date, account_id, cash_balance)

New schema: see models.py. Table/column names differ enough that only
`banks`, `currencies`, and `bank_dues` happen to already match; everything
else needs either a rename+remap or a fresh table (new table name, so no
collision -- e.g. `bus` -> `business_units`, `exchange_rates` -> `fx_rates`,
`daily_cash_positions` -> `receivables_daily`).
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("migrate_legacy")

OLD_ROLE_MAP = {
    "Manager": "Manager",
    "Read/Write": "ReadWrite",
    "Read-Only": "ReadOnly",
}


def _table_columns(inspector, table_name):
    if table_name not in inspector.get_table_names():
        return None
    return {c["name"] for c in inspector.get_columns(table_name)}


def prepare_legacy_rename(engine: Engine) -> bool:
    """MUST run before Base.metadata.create_all(). Handles every case where
    an old-app table shares its name with a new-shaped table, since
    create_all() only creates missing tables -- it never alters an existing
    one's columns. Two cases:

      1. 'master_accounts' shape is fundamentally incompatible (free-text
         bu/department vs FK columns) -- renamed out of the way so
         create_all can build the new-shaped table fresh under that name.
      2. 'users' is almost the same shape, just missing the new
         'created_at' column -- patched in place with ALTER TABLE rather
         than renamed, since everything else about it (including its data)
         is directly reusable.

    Returns True if any legacy schema was detected at all (drives whether
    run_legacy_migration() has real migration work to do afterwards)."""
    inspector = inspect(engine)

    master_accounts_cols = _table_columns(inspector, "master_accounts")
    is_legacy_master_accounts = master_accounts_cols is not None and (
        "business_unit_id" not in master_accounts_cols
    )
    if is_legacy_master_accounts:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE master_accounts RENAME TO master_accounts_legacy"))

    user_cols = _table_columns(inspector, "users")
    is_legacy_users = user_cols is not None and "created_at" not in user_cols
    if is_legacy_users:
        with engine.begin() as conn:
            # Postgres and SQLite both accept this form (no IF NOT EXISTS
            # needed since we already confirmed the column is absent).
            conn.execute(text("ALTER TABLE users ADD COLUMN created_at TIMESTAMP"))

    return (
        is_legacy_master_accounts
        or is_legacy_users
        or "bus" in inspector.get_table_names()
    )


def run_legacy_migration(engine: Engine, legacy_present: bool) -> list[str]:
    """Call AFTER Base.metadata.create_all(). Returns a list of human-readable
    log lines describing what happened, so the caller (main.py) can print/log
    a startup summary."""
    report: list[str] = []
    inspector = inspect(engine)

    if not legacy_present:
        report.append("No legacy schema detected -- starting from a fresh database.")
        return report

    is_legacy_master_accounts = "master_accounts_legacy" in inspector.get_table_names()

    report.append("Legacy schema detected -- migrating into the new structure.")

    with engine.begin() as conn:
        # ---- 1. Business Units: bus -> business_units -----------------
        bu_name_to_new_id: dict[str, int] = {}
        if "bus" in inspector.get_table_names():
            rows = conn.execute(text("SELECT id, name FROM bus")).fetchall()
            for old_id, name in rows:
                existing = conn.execute(
                    text("SELECT id FROM business_units WHERE name = :n"), {"n": name}
                ).fetchone()
                if existing:
                    bu_name_to_new_id[name] = existing[0]
                else:
                    result = conn.execute(
                        text("INSERT INTO business_units (name) VALUES (:n)"), {"n": name}
                    )
                    bu_name_to_new_id[name] = result.lastrowid if result.lastrowid else None
            # Postgres doesn't populate lastrowid; re-select to be safe.
            if bu_name_to_new_id and any(v is None for v in bu_name_to_new_id.values()):
                for name in list(bu_name_to_new_id.keys()):
                    row = conn.execute(
                        text("SELECT id FROM business_units WHERE name = :n"), {"n": name}
                    ).fetchone()
                    bu_name_to_new_id[name] = row[0]
            report.append(f"Migrated {len(bu_name_to_new_id)} business unit(s) from 'bus'.")

        # Fallback BU for accounts whose old 'bu' value doesn't match any
        # migrated name (shouldn't normally happen).
        def get_or_create_bu(name: str) -> int:
            name = name or "Unassigned"
            if name in bu_name_to_new_id:
                return bu_name_to_new_id[name]
            existing = conn.execute(
                text("SELECT id FROM business_units WHERE name = :n"), {"n": name}
            ).fetchone()
            if existing:
                bu_name_to_new_id[name] = existing[0]
                return existing[0]
            result = conn.execute(
                text("INSERT INTO business_units (name) VALUES (:n)"), {"n": name}
            )
            row = conn.execute(
                text("SELECT id FROM business_units WHERE name = :n"), {"n": name}
            ).fetchone()
            bu_name_to_new_id[name] = row[0]
            return row[0]

        # ---- 2. Divisions: old free-text 'department' -> divisions ----
        division_key_to_id: dict[tuple, int] = {}

        def get_or_create_division(dept_name: str, bu_id: int) -> int:
            dept_name = dept_name or "General"
            key = (dept_name, bu_id)
            if key in division_key_to_id:
                return division_key_to_id[key]
            existing = conn.execute(
                text(
                    "SELECT id FROM divisions WHERE name = :n AND business_unit_id = :b"
                ),
                {"n": dept_name, "b": bu_id},
            ).fetchone()
            if existing:
                division_key_to_id[key] = existing[0]
                return existing[0]
            conn.execute(
                text(
                    "INSERT INTO divisions (name, business_unit_id) VALUES (:n, :b)"
                ),
                {"n": dept_name, "b": bu_id},
            )
            row = conn.execute(
                text(
                    "SELECT id FROM divisions WHERE name = :n AND business_unit_id = :b"
                ),
                {"n": dept_name, "b": bu_id},
            ).fetchone()
            division_key_to_id[key] = row[0]
            return row[0]

        # ---- 3. banks / currencies already share the same shape -- no-op

        # ---- 4. Master accounts: migrate rows from the renamed legacy table
        # (the rename itself already happened in prepare_legacy_rename(),
        # and Base.metadata.create_all() already built the new-shaped table)
        if is_legacy_master_accounts:
            old_accounts = conn.execute(
                text(
                    "SELECT id, bu, department, bank_shortname, account_number,"
                    " account_name, currency FROM master_accounts_legacy"
                )
            ).fetchall()
            migrated = 0
            for (
                old_id,
                bu_name,
                dept,
                bank_shortname,
                acc_num,
                acc_name,
                currency,
            ) in old_accounts:
                # master_accounts_legacy is kept around permanently (not
                # dropped, by design -- see module docstring), which means
                # this loop runs again on every future restart too. Skip
                # rows already migrated so restarts stay idempotent instead
                # of hitting a duplicate primary key.
                already = conn.execute(
                    text("SELECT 1 FROM master_accounts WHERE id = :id"), {"id": old_id}
                ).fetchone()
                if already:
                    continue
                bu_id = get_or_create_bu(bu_name)
                div_id = get_or_create_division(dept, bu_id)
                bank_row = conn.execute(
                    text("SELECT id FROM banks WHERE short_name = :s"),
                    {"s": bank_shortname},
                ).fetchone()
                if not bank_row:
                    conn.execute(
                        text(
                            "INSERT INTO banks (short_name, full_name) VALUES (:s, :f)"
                        ),
                        {"s": bank_shortname or "UNKNOWN", "f": bank_shortname or "Unknown Bank"},
                    )
                    bank_row = conn.execute(
                        text("SELECT id FROM banks WHERE short_name = :s"),
                        {"s": bank_shortname},
                    ).fetchone()
                bank_id = bank_row[0]
                # Preserve original id so bank_dues.account_id /
                # daily_cash_positions.account_id keep resolving correctly.
                conn.execute(
                    text(
                        """
                        INSERT INTO master_accounts
                            (id, business_unit_id, division_id, bank_id,
                             account_name, account_number, currency)
                        VALUES (:id, :bu, :div, :bank, :aname, :anum, :curr)
                        """
                    ),
                    {
                        "id": old_id,
                        "bu": bu_id,
                        "div": div_id,
                        "bank": bank_id,
                        "aname": acc_name,
                        "anum": acc_num,
                        "curr": currency,
                    },
                )
                migrated += 1
            report.append(
                f"Migrated {migrated} master account(s) (old table kept as"
                " 'master_accounts_legacy')."
            )

        # ---- 5. Exchange rates: exchange_rates -> fx_rates -------------
        if "exchange_rates" in inspector.get_table_names() and "fx_rates" in inspector.get_table_names():
            old_rates = conn.execute(
                text(
                    "SELECT rate_date, currency_pair, rate, is_auto_filled FROM"
                    " exchange_rates"
                )
            ).fetchall()
            pair_cache: dict[str, int] = {}
            migrated_rates = 0
            for rate_date, pair_label, rate, is_auto_filled in old_rates:
                if "/" not in (pair_label or ""):
                    continue
                base, quote = pair_label.split("/", 1)
                if pair_label not in pair_cache:
                    existing = conn.execute(
                        text(
                            "SELECT id FROM currency_pairs WHERE base_currency = :b"
                            " AND quote_currency = :q"
                        ),
                        {"b": base, "q": quote},
                    ).fetchone()
                    if existing:
                        pair_cache[pair_label] = existing[0]
                    else:
                        extended = "SDG" in (base, quote)
                        conn.execute(
                            text(
                                "INSERT INTO currency_pairs (base_currency,"
                                " quote_currency, supports_extended_rates,"
                                " is_default) VALUES (:b, :q, :ext, false)"
                            ),
                            {"b": base, "q": quote, "ext": extended},
                        )
                        row = conn.execute(
                            text(
                                "SELECT id FROM currency_pairs WHERE"
                                " base_currency = :b AND quote_currency = :q"
                            ),
                            {"b": base, "q": quote},
                        ).fetchone()
                        pair_cache[pair_label] = row[0]
                conn.execute(
                    text(
                        """
                        INSERT INTO fx_rates
                            (rate_date, currency_pair_id, rate_type, rate, is_manual_entry)
                        VALUES (:d, :p, 'Market', :r, :manual)
                        ON CONFLICT (rate_date, currency_pair_id, rate_type) DO NOTHING
                        """
                    ),
                    {
                        "d": rate_date,
                        "p": pair_cache[pair_label],
                        "r": rate,
                        "manual": not bool(is_auto_filled),
                    },
                )
                migrated_rates += 1
            report.append(
                f"Migrated {migrated_rates} FX rate row(s) from 'exchange_rates' as"
                " Market Rate entries."
            )

        # ---- 6. Cash positions -> receivables_daily --------------------
        if (
            "daily_cash_positions" in inspector.get_table_names()
            and "receivables_daily" in inspector.get_table_names()
        ):
            old_cash = conn.execute(
                text(
                    "SELECT position_date, account_id, cash_balance FROM"
                    " daily_cash_positions"
                )
            ).fetchall()
            migrated_cash = 0
            for position_date, account_id, cash_balance in old_cash:
                conn.execute(
                    text(
                        """
                        INSERT INTO receivables_daily (position_date, account_id, amount)
                        VALUES (:d, :a, :amt)
                        ON CONFLICT (position_date, account_id) DO NOTHING
                        """
                    ),
                    {"d": position_date, "a": account_id, "amt": cash_balance},
                )
                migrated_cash += 1
            report.append(
                f"Migrated {migrated_cash} daily cash position row(s) into"
                " 'receivables_daily'."
            )

        # ---- 7. Users: sha256 passwords can't be verified as bcrypt ----
        # IMPORTANT: this isn't just a "reset it later" inconvenience -- if
        # left as-is, EVERY migrated user is permanently locked out, and
        # since the Settings > User Management UI that could reset a
        # password doesn't exist until Phase 5, and reaching it requires
        # already being logged in as a Manager, a fully broken hash means
        # nobody can ever log in to fix it. So: any hash that isn't already
        # a bcrypt hash (bcrypt hashes always start with $2) is reset to a
        # known bootstrap password instead of left broken. This is
        # imported lazily to avoid a circular import at module load time.
        from .auth import hash_password
        from .config import DEFAULT_ADMIN_PASSWORD

        user_cols = _table_columns(inspector, "users")
        if user_cols:
            users = conn.execute(
                text("SELECT id, username, role, password_hash FROM users")
            ).fetchall()
            reset_usernames = []
            for uid, username, old_role, pw_hash in users:
                new_role = OLD_ROLE_MAP.get(old_role, "ReadWrite")
                if new_role != old_role:
                    conn.execute(
                        text("UPDATE users SET role = :r WHERE id = :id"),
                        {"r": new_role, "id": uid},
                    )
                if not (pw_hash or "").startswith("$2"):
                    conn.execute(
                        text("UPDATE users SET password_hash = :h WHERE id = :id"),
                        {"h": hash_password(DEFAULT_ADMIN_PASSWORD), "id": uid},
                    )
                    reset_usernames.append(username)
            report.append(f"Normalized roles for {len(users)} existing user(s).")
            if reset_usernames:
                report.append(
                    f"SECURITY: reset password for {len(reset_usernames)} migrated"
                    f" user(s) to the bootstrap default ({', '.join(reset_usernames)})"
                    " because their old SHA256 hash can't be verified under the new"
                    " bcrypt scheme. Log in and change these immediately -- everyone"
                    " listed currently shares the same known password."
                )

    return report
