from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..config import NON_SDG_RATE_TYPES, SDG_RATE_TYPES
from ..database import get_db
from ..export_utils import read_uploaded_xlsx, xlsx_response, xlsx_template_response
from ..rates import build_daily_series, get_pair

router = APIRouter(prefix="/api/fx", tags=["fx"])

FX_TEMPLATE_COLUMNS = ["Date", "Base Currency", "Quote Currency", "Rate Type", "Rate"]

# str.title() mangles acronyms ("CBOS".title() == "Cbos"), so rate types
# from an upload are normalized via this explicit case-insensitive map
# instead, rather than relying on .title()/.capitalize().
_RATE_TYPE_CANONICAL = {t.lower(): t for t in SDG_RATE_TYPES}


def _normalize_rate_type(raw: str) -> str | None:
    return _RATE_TYPE_CANONICAL.get(str(raw).strip().lower())


@router.get("/rate-types")
def rate_types(pair_id: int, db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    pair = db.query(models.CurrencyPair).get(pair_id)
    if not pair:
        raise HTTPException(404, "Unknown currency pair.")
    return SDG_RATE_TYPES if pair.supports_extended_rates else NON_SDG_RATE_TYPES


@router.post("/rates", response_model=schemas.FxRateOut)
def record_rate(
    payload: schemas.FxRateCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    pair = db.query(models.CurrencyPair).get(payload.currency_pair_id)
    if not pair:
        raise HTTPException(400, "Unknown currency pair.")
    allowed_types = SDG_RATE_TYPES if pair.supports_extended_rates else NON_SDG_RATE_TYPES
    if payload.rate_type not in allowed_types:
        raise HTTPException(
            400, f"{pair.label} only supports rate types: {', '.join(allowed_types)}"
        )

    existing = (
        db.query(models.FxRate)
        .filter(
            models.FxRate.rate_date == payload.rate_date,
            models.FxRate.currency_pair_id == payload.currency_pair_id,
            models.FxRate.rate_type == payload.rate_type,
        )
        .first()
    )
    if existing:
        existing.rate = payload.rate
        existing.is_manual_entry = True
    else:
        existing = models.FxRate(
            rate_date=payload.rate_date,
            currency_pair_id=payload.currency_pair_id,
            rate_type=payload.rate_type,
            rate=payload.rate,
            is_manual_entry=True,
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return schemas.FxRateOut(
        rate_date=existing.rate_date,
        currency_pair=pair.label,
        rate_type=existing.rate_type,
        rate=existing.rate,
        is_carried_forward=False,
    )


@router.get("/rates/table", response_model=list[schemas.FxRateOut])
def rates_table(
    currency_pair_id: int,
    rate_type: str = "Market",
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    """Daily series with carry-forward fill, used both for the FX Rates
    page's current-month table (and collapsed prior months) and for
    Analysis charts."""
    pair = db.query(models.CurrencyPair).get(currency_pair_id)
    if not pair:
        raise HTTPException(404, "Unknown currency pair.")
    series = build_daily_series(db, pair.base_currency, pair.quote_currency, rate_type, start, end)
    return [
        schemas.FxRateOut(
            rate_date=row["rate_date"],
            currency_pair=pair.label,
            rate_type=rate_type,
            rate=row["rate"],
            is_carried_forward=row["is_carried_forward"],
        )
        for row in series
    ]


@router.get("/rates/table/export")
def export_rates_table(
    currency_pair_id: int,
    rate_type: str = "Market",
    start: date = Query(...),
    end: date = Query(...),
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    pair = db.query(models.CurrencyPair).get(currency_pair_id)
    if not pair:
        raise HTTPException(404, "Unknown currency pair.")
    series = build_daily_series(db, pair.base_currency, pair.quote_currency, rate_type, start, end)
    rows = [
        {
            "Date": row["rate_date"],
            "Pair": pair.label,
            "Rate Type": rate_type,
            "Rate": float(row["rate"]),
            "Carried Forward": row["is_carried_forward"],
        }
        for row in series
    ]
    return xlsx_response(rows, f"fx_rates_{pair.label.replace('/', '')}_{rate_type}.xlsx")


@router.get("/import/template")
def fx_import_template(_u: models.User = Depends(get_current_user)):
    example_rows = [
        ["2026-08-24", "AED", "SDG", "Market", 981.20],
        ["2026-08-25", "AED", "SDG", "Market", 982.00],
        ["2026-08-25", "AED", "SDG", "CBOS", 970.00],
        ["2026-08-25", "AED", "SDG", "Pricing", 985.50],
        ["2026-08-25", "USD", "SDG", "Market", 3610.00],
    ]
    notes = [
        "Date must be YYYY-MM-DD (or any format Excel stores as a real date).",
        "Base Currency / Quote Currency: e.g. AED / SDG. Currency codes should already exist"
        " under Settings > Currencies, or be added there first -- unknown codes are skipped.",
        "Currency pairs are created automatically the first time they appear here if they"
        " don't exist yet.",
        "Rate Type must be exactly one of: Market, CBOS, Pricing. CBOS and Pricing are only"
        " valid for a pair where SDG is the base or quote currency -- rows using them for a"
        " non-SDG pair (e.g. USD/EUR) are skipped.",
        "Uploading a row for a Date + Pair + Rate Type that already has a rate on file UPDATES"
        " that rate (replaces the value) rather than creating a duplicate. This is how you"
        " correct a mistake or replace test data with final figures -- just re-upload with the"
        " corrected value.",
        "Rate is a plain number, e.g. 982.00 -- no currency symbols or thousands separators.",
    ]
    return xlsx_template_response(FX_TEMPLATE_COLUMNS, example_rows, notes, "fx_rates_template.xlsx")


@router.post("/import", response_model=schemas.ImportResult)
def fx_import(
    file: UploadFile,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    try:
        df = read_uploaded_xlsx(file.file.read())
    except Exception as e:
        raise HTTPException(400, f"Couldn't read this file as an Excel workbook: {e}")

    missing = [c for c in FX_TEMPLATE_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(
            400,
            f"Missing column(s): {', '.join(missing)}. Download the template to see the"
            " expected columns.",
        )

    imported = 0
    updated = 0
    errors: list[schemas.ImportRowError] = []
    pair_cache: dict[tuple, models.CurrencyPair] = {}

    for idx, row in df.iterrows():
        row_number = idx + 2  # header is row 1, pandas is 0-indexed
        try:
            raw_date = row["Date"]
            rate_date = (
                raw_date.date() if hasattr(raw_date, "date") else pd.to_datetime(raw_date).date()
            )
            base = str(row["Base Currency"]).strip().upper()
            quote = str(row["Quote Currency"]).strip().upper()
            rate_type = _normalize_rate_type(row["Rate Type"])
            rate = Decimal(str(row["Rate"]))
        except (ValueError, InvalidOperation, TypeError) as e:
            errors.append(schemas.ImportRowError(row_number=row_number, reason=f"Couldn't parse row: {e}"))
            continue

        if rate_type is None:
            errors.append(
                schemas.ImportRowError(
                    row_number=row_number,
                    reason=f"Rate Type '{row['Rate Type']}' isn't recognized -- must be Market, CBOS, or Pricing.",
                )
            )
            continue

        if not db.query(models.Currency).get(base) or not db.query(models.Currency).get(quote):
            errors.append(
                schemas.ImportRowError(
                    row_number=row_number,
                    reason=f"Unknown currency code ({base} or {quote}) -- add it under Settings first.",
                )
            )
            continue

        cache_key = (base, quote)
        pair = pair_cache.get(cache_key) or get_pair(db, base, quote)
        if not pair:
            pair = models.CurrencyPair(
                base_currency=base,
                quote_currency=quote,
                supports_extended_rates="SDG" in (base, quote),
                is_default=False,
            )
            db.add(pair)
            db.flush()
        pair_cache[cache_key] = pair

        allowed_types = SDG_RATE_TYPES if pair.supports_extended_rates else NON_SDG_RATE_TYPES
        if rate_type not in allowed_types:
            errors.append(
                schemas.ImportRowError(
                    row_number=row_number,
                    reason=f"Rate Type '{rate_type}' isn't valid for {pair.label} (allowed: {', '.join(allowed_types)}).",
                )
            )
            continue

        existing = (
            db.query(models.FxRate)
            .filter(
                models.FxRate.rate_date == rate_date,
                models.FxRate.currency_pair_id == pair.id,
                models.FxRate.rate_type == rate_type,
            )
            .first()
        )
        if existing:
            existing.rate = rate
            existing.is_manual_entry = True
            updated += 1
        else:
            db.add(
                models.FxRate(
                    rate_date=rate_date,
                    currency_pair_id=pair.id,
                    rate_type=rate_type,
                    rate=rate,
                    is_manual_entry=True,
                )
            )
            imported += 1

    db.commit()
    return schemas.ImportResult(imported=imported, updated=updated, skipped=errors)
