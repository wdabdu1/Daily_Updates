"""Startup sequence: prepare any legacy-schema rename, create all tables,
run the legacy data migration, then seed defaults (admin user, currency
list, default AED/SDG pair) -- but only where they don't already exist.

Unlike the old app, this NEVER resets an existing admin password on
restart. The default admin/admin123 user is only created once, the first
time the users table is completely empty.
"""
import logging

from sqlalchemy import inspect

from .auth import hash_password
from .config import DEFAULT_ADMIN_PASSWORD, DEFAULT_ADMIN_USERNAME, SEED_CURRENCIES
from .database import Base, SessionLocal, engine
from . import models
from .migrate_legacy import prepare_legacy_rename, run_legacy_migration
from .schema_upgrades import apply_schema_upgrades

logger = logging.getLogger("seed")


def init_db():
    legacy_present = prepare_legacy_rename(engine)
    Base.metadata.create_all(bind=engine)
    report = run_legacy_migration(engine, legacy_present)
    for line in report:
        logger.info(line)

    # Runs regardless of legacy_present -- these patch the CURRENT schema,
    # not a migration from the old app's schema.
    for line in apply_schema_upgrades(engine):
        logger.info(line)

    db = SessionLocal()
    try:
        # Seed the default admin ONLY if there are truly no users yet --
        # this is the fix for the old app's bug where init_db() reset the
        # admin password on every single restart.
        if db.query(models.User).count() == 0:
            db.add(
                models.User(
                    username=DEFAULT_ADMIN_USERNAME,
                    password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                    role="Manager",
                )
            )
            logger.info(
                f"No users found -- created default Manager user"
                f" '{DEFAULT_ADMIN_USERNAME}'. Change this password immediately"
                " after first login."
            )

        for code in SEED_CURRENCIES:
            if not db.query(models.Currency).filter(models.Currency.code == code).first():
                db.add(models.Currency(code=code))

        db.commit()

        # Seed the default AED/SDG pair if no pairs exist at all yet.
        if db.query(models.CurrencyPair).count() == 0:
            db.add(
                models.CurrencyPair(
                    base_currency="AED",
                    quote_currency="SDG",
                    supports_extended_rates=True,
                    is_default=True,
                )
            )
            db.commit()
    finally:
        db.close()
