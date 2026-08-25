"""Optional: populate a handful of demo rows so the UI has something to
show while reviewing Phase 1, WITHOUT waiting for the Settings pages to be
built (Phase 5). Safe to run multiple times (checks before inserting).
Run manually: `python -m app.seed_demo` from backend/.

This is demo data only -- delete it (or just reset the database) before
going to production.
"""
from datetime import date, timedelta
from decimal import Decimal

from .database import SessionLocal
from . import models
from .seed import init_db


def get_or_create(db, model, defaults=None, **kwargs):
    instance = db.query(model).filter_by(**kwargs).first()
    if instance:
        return instance, False
    params = dict(kwargs)
    params.update(defaults or {})
    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance, True


def run():
    init_db()
    db = SessionLocal()
    try:
        bu_treasury, _ = get_or_create(db, models.BusinessUnit, name="Corporate Treasury")
        bu_logistics, _ = get_or_create(db, models.BusinessUnit, name="Logistics")

        div_ops, _ = get_or_create(
            db, models.Division, name="Operations", business_unit_id=bu_treasury.id
        )
        div_freight, _ = get_or_create(
            db, models.Division, name="Freight", business_unit_id=bu_logistics.id
        )

        bank_cib, _ = get_or_create(
            db, models.Bank, short_name="CIB", defaults={"full_name": "Commercial International Bank"}
        )
        bank_omdurman, _ = get_or_create(
            db, models.Bank, short_name="ONB", defaults={"full_name": "Omdurman National Bank"}
        )

        pair_aed_sdg = (
            db.query(models.CurrencyPair)
            .filter(
                models.CurrencyPair.base_currency == "AED",
                models.CurrencyPair.quote_currency == "SDG",
            )
            .first()
        )
        pair_usd_sdg, _ = get_or_create(
            db,
            models.CurrencyPair,
            base_currency="USD",
            quote_currency="SDG",
            defaults={"supports_extended_rates": True, "is_default": False},
        )

        acc1, _ = get_or_create(
            db,
            models.MasterAccount,
            account_number="1001-AED",
            defaults={
                "business_unit_id": bu_treasury.id,
                "division_id": div_ops.id,
                "bank_id": bank_cib.id,
                "account_name": "Treasury Main AED",
                "currency": "SDG",
            },
        )
        acc2, _ = get_or_create(
            db,
            models.MasterAccount,
            account_number="2002-SDG",
            defaults={
                "business_unit_id": bu_logistics.id,
                "division_id": div_freight.id,
                "bank_id": bank_omdurman.id,
                "account_name": "Freight Ops SDG",
                "currency": "SDG",
            },
        )
        db.commit()

        today = date.today()
        for days_ago, aed_sdg, usd_sdg in [
            (2, Decimal("980.5000"), Decimal("3601.0000")),
            (1, Decimal("981.2000"), Decimal("3605.5000")),
            (0, Decimal("982.0000"), Decimal("3610.0000")),
        ]:
            d = today - timedelta(days=days_ago)
            if pair_aed_sdg:
                get_or_create(
                    db,
                    models.FxRate,
                    rate_date=d,
                    currency_pair_id=pair_aed_sdg.id,
                    rate_type="Market",
                    defaults={"rate": aed_sdg},
                )
            get_or_create(
                db,
                models.FxRate,
                rate_date=d,
                currency_pair_id=pair_usd_sdg.id,
                rate_type="Market",
                defaults={"rate": usd_sdg},
            )
        db.commit()

        for days_ago, amt1, amt2 in [(1, Decimal("450000"), Decimal("120000")), (0, Decimal("470000"), Decimal("115000"))]:
            d = today - timedelta(days=days_ago)
            get_or_create(
                db,
                models.ReceivableDaily,
                position_date=d,
                account_id=acc1.id,
                defaults={"amount": amt1},
            )
            get_or_create(
                db,
                models.ReceivableDaily,
                position_date=d,
                account_id=acc2.id,
                defaults={"amount": amt2},
            )
        db.commit()

        get_or_create(
            db,
            models.BankDue,
            account_id=acc1.id,
            due_date=today + timedelta(days=10),
            defaults={"facility_type": "Overdraft", "amount": Decimal("300000"), "status": "Active"},
        )
        get_or_create(
            db,
            models.BankDue,
            account_id=acc2.id,
            due_date=today + timedelta(days=20),
            defaults={"facility_type": "Trade Finance", "amount": Decimal("250000"), "status": "Active"},
        )
        db.commit()
        print("Demo data seeded.")
    finally:
        db.close()


if __name__ == "__main__":
    run()
