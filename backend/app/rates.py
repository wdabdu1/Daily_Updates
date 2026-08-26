"""Shared FX rate lookup / carry-forward helpers.

Convention: for a pair labeled BASE/QUOTE (e.g. USD/SDG), `rate` means
"1 BASE = rate QUOTE" -- e.g. USD/SDG = 3600 means 1 USD costs 3600 SDG.
This matches how the business actually talks about it (SDG is the volatile
local currency priced *against* a harder currency).
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from . import models


def get_pair(db: Session, base: str, quote: str) -> models.CurrencyPair | None:
    return (
        db.query(models.CurrencyPair)
        .filter(
            models.CurrencyPair.base_currency == base,
            models.CurrencyPair.quote_currency == quote,
        )
        .first()
    )


def get_latest_rate(
    db: Session, base: str, quote: str, rate_type: str = "Market", as_of: date | None = None
) -> tuple[Decimal, date] | tuple[None, None]:
    """Latest known rate for (base/quote, rate_type) on or before `as_of`
    (defaults to today). This *is* the carry-forward behavior for a single
    point-in-time lookup: whatever was last entered stays "current" until a
    newer entry supersedes it."""
    pair = get_pair(db, base, quote)
    if not pair:
        return None, None
    as_of = as_of or date.today()
    row = (
        db.query(models.FxRate)
        .filter(
            models.FxRate.currency_pair_id == pair.id,
            models.FxRate.rate_type == rate_type,
            models.FxRate.rate_date <= as_of,
        )
        .order_by(models.FxRate.rate_date.desc())
        .first()
    )
    if not row:
        return None, None
    return row.rate, row.rate_date


def build_daily_series(
    db: Session,
    base: str,
    quote: str,
    rate_type: str,
    start: date,
    end: date,
) -> list[dict]:
    """Every calendar day from start..end for this (pair, rate_type), with
    gaps filled from the most recent prior actual entry. Each row is
    flagged is_carried_forward so the UI can render it distinctly (e.g.
    greyed out / italic) from a day someone actually entered a rate for."""
    pair = get_pair(db, base, quote)
    if not pair:
        return []

    actual_rows = (
        db.query(models.FxRate)
        .filter(
            models.FxRate.currency_pair_id == pair.id,
            models.FxRate.rate_type == rate_type,
            models.FxRate.rate_date <= end,
        )
        .order_by(models.FxRate.rate_date.asc())
        .all()
    )
    # Keep the row id alongside the rate -- callers use it to let a user
    # edit/delete a specific *actual* entry (a carried-forward day has no id
    # of its own, since it isn't a stored row).
    by_date = {r.rate_date: (r.rate, r.id) for r in actual_rows}

    # Seed with the most recent actual rate at or before `start`, if any,
    # so the very first day of the window can still be carried forward.
    last_rate = None
    for r in actual_rows:
        if r.rate_date <= start:
            last_rate = r.rate
        else:
            break

    series = []
    d = start
    while d <= end:
        if d in by_date:
            last_rate, row_id = by_date[d]
            series.append(
                {"rate_date": d, "rate": last_rate, "is_carried_forward": False, "id": row_id}
            )
        elif last_rate is not None:
            series.append(
                {"rate_date": d, "rate": last_rate, "is_carried_forward": True, "id": None}
            )
        # else: no rate known yet at all for this date -- omit rather than
        # show a fabricated zero.
        d += timedelta(days=1)
    return series
