from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..database import get_db
from .receivables import _division_options

# ---------------------------------------------------------------------------
# Round 13: Cash Balances. Exact mirror of receivables.py's /divisions/*
# sub-path (form / save / table), just reading and writing
# DivisionCashBalanceDaily instead of DivisionReceivableDaily -- same
# prefill-from-latest-earlier-snapshot workflow, same generic schemas (a
# division amount snapshot has an identical shape whether it's a PDC
# position or a cash balance, so nothing new was needed in schemas.py for
# this router). The division list itself isn't duplicated here -- the
# frontend reuses GET /api/receivables/divisions/list, since "every
# division" doesn't differ between the two features.
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/cash", tags=["cash"])


@router.get("/divisions/form", response_model=list[schemas.DivisionReceivableFormRow])
def get_division_cash_form(
    position_date: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    """Powers 'Today's Update' for Cash Balances: every division, pre-filled
    with its most recent recorded cash position on or before `position_date`
    (defaults to today)."""
    divisions = _division_options(db)
    rows = []
    for d in divisions:
        last = (
            db.query(models.DivisionCashBalanceDaily)
            .filter(
                models.DivisionCashBalanceDaily.division_id == d.id,
                models.DivisionCashBalanceDaily.position_date <= position_date,
            )
            .order_by(models.DivisionCashBalanceDaily.position_date.desc())
            .first()
        )
        rows.append(
            schemas.DivisionReceivableFormRow(
                division_id=d.id,
                division_name=d.name,
                business_unit_name=d.business_unit.name if d.business_unit else "",
                default_amount=last.amount if last else Decimal("0"),
                default_amount_date=last.position_date if last else None,
                is_recorded_for_date=bool(last and last.position_date == position_date),
            )
        )
    return rows


@router.post("/divisions/save")
def save_division_cash(
    payload: schemas.DivisionReceivableSaveRequest,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    valid_ids = {d.id for d in db.query(models.Division.id).all()}
    unknown = [r.division_id for r in payload.rows if r.division_id not in valid_ids]
    if unknown:
        raise HTTPException(400, f"Unknown division id(s): {', '.join(map(str, unknown))}.")

    for row in payload.rows:
        existing = (
            db.query(models.DivisionCashBalanceDaily)
            .filter(
                models.DivisionCashBalanceDaily.position_date == payload.position_date,
                models.DivisionCashBalanceDaily.division_id == row.division_id,
            )
            .first()
        )
        if existing:
            existing.amount = row.amount
        else:
            db.add(
                models.DivisionCashBalanceDaily(
                    position_date=payload.position_date,
                    division_id=row.division_id,
                    amount=row.amount,
                )
            )
    db.commit()
    return {"saved": len(payload.rows), "position_date": payload.position_date}


@router.get("/divisions/table", response_model=list[schemas.DivisionReceivableTableRow])
def division_cash_table(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    """The full Date x Division cash-balance history, most recent first --
    only actual recorded entries appear, same no-carry-forward-fill
    convention as the PDC history table."""
    q = db.query(models.DivisionCashBalanceDaily)
    if start:
        q = q.filter(models.DivisionCashBalanceDaily.position_date >= start)
    if end:
        q = q.filter(models.DivisionCashBalanceDaily.position_date <= end)
    entries = q.order_by(models.DivisionCashBalanceDaily.position_date.desc()).all()

    by_date: dict[date, dict[str, Decimal]] = {}
    for e in entries:
        by_date.setdefault(e.position_date, {})[str(e.division_id)] = e.amount

    return [
        schemas.DivisionReceivableTableRow(
            position_date=d,
            amounts=amounts,
            total=sum(amounts.values(), Decimal("0")),
        )
        for d, amounts in sorted(by_date.items(), key=lambda kv: kv[0], reverse=True)
    ]
