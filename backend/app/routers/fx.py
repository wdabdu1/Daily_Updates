from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..config import NON_SDG_RATE_TYPES, SDG_RATE_TYPES
from ..database import get_db
from ..export_utils import xlsx_response
from ..rates import build_daily_series, get_pair

router = APIRouter(prefix="/api/fx", tags=["fx"])


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
