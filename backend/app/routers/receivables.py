from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..database import get_db

router = APIRouter(prefix="/api/receivables", tags=["receivables"])


class ReceivableFormRow(BaseModel):
    account_id: int
    business_unit_name: str
    division_name: str
    bank_short_name: str
    account_name: str
    account_number: str
    currency: str
    default_amount: Decimal
    default_amount_date: date | None
    # True when default_amount_date == the requested position_date, i.e. an
    # entry for that exact day already exists and saving will UPDATE it
    # rather than fall back to an earlier day's figure as a starting point.
    is_recorded_for_date: bool


@router.get("/form", response_model=list[ReceivableFormRow])
def get_form(
    position_date: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    """Powers the 'Start Update' / 'Edit a past day' workflow: every
    account, pre-filled with its most recent snapshot amount on or before
    `position_date` (defaults to today). Passing a past date lets you
    reopen and correct that day's entries specifically -- if that account
    already has a snapshot for that exact date, that's what's prefilled
    (is_recorded_for_date=True); otherwise it falls back to the latest
    earlier snapshot, same as the original "start update" behavior."""
    accounts = (
        db.query(models.MasterAccount)
        .options(
            joinedload(models.MasterAccount.business_unit),
            joinedload(models.MasterAccount.division),
            joinedload(models.MasterAccount.bank),
        )
        .all()
    )
    rows = []
    for a in accounts:
        last = (
            db.query(models.ReceivableDaily)
            .filter(
                models.ReceivableDaily.account_id == a.id,
                models.ReceivableDaily.position_date <= position_date,
            )
            .order_by(models.ReceivableDaily.position_date.desc())
            .first()
        )
        rows.append(
            ReceivableFormRow(
                account_id=a.id,
                business_unit_name=a.business_unit.name if a.business_unit else "",
                division_name=a.division.name if a.division else "",
                bank_short_name=a.bank.short_name if a.bank else "",
                account_name=a.account_name,
                account_number=a.account_number,
                currency=a.currency,
                default_amount=last.amount if last else Decimal("0"),
                default_amount_date=last.position_date if last else None,
                is_recorded_for_date=bool(last and last.position_date == position_date),
            )
        )
    return rows


@router.post("/save")
def save(
    payload: schemas.ReceivableSaveRequest,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    for row in payload.rows:
        existing = (
            db.query(models.ReceivableDaily)
            .filter(
                models.ReceivableDaily.position_date == payload.position_date,
                models.ReceivableDaily.account_id == row.account_id,
            )
            .first()
        )
        if existing:
            existing.amount = row.amount
        else:
            db.add(
                models.ReceivableDaily(
                    position_date=payload.position_date,
                    account_id=row.account_id,
                    amount=row.amount,
                )
            )
    db.commit()
    return {"saved": len(payload.rows), "position_date": payload.position_date}


# ---------------------------------------------------------------------------
# Round 11: division-based receivables. Replaces the account/bank-linked
# workflow above as the thing Home/Analysis actually read -- see
# DivisionReceivableDaily's docstring in models.py for why. Kept under the
# same /api/receivables prefix but a distinct /divisions/* sub-path so the
# legacy endpoints above stay untouched and reachable (nothing was asked to
# be deleted, and their history stays queryable even though the UI no
# longer calls them).
# ---------------------------------------------------------------------------


def _division_options(db: Session) -> list[models.Division]:
    return (
        db.query(models.Division)
        .options(joinedload(models.Division.business_unit))
        .order_by(models.Division.name)
        .all()
    )


@router.get("/divisions/list", response_model=list[schemas.DivisionOption])
def list_divisions(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return [
        schemas.DivisionOption(
            id=d.id,
            name=d.name,
            business_unit_id=d.business_unit_id,
            business_unit_name=d.business_unit.name if d.business_unit else "",
        )
        for d in _division_options(db)
    ]


@router.get("/divisions/form", response_model=list[schemas.DivisionReceivableFormRow])
def get_division_form(
    position_date: date = Query(default_factory=date.today),
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    """Powers 'Today's Update': every division, pre-filled with its most
    recent recorded position on or before `position_date` (defaults to
    today) -- same prefill-from-latest-earlier-snapshot pattern the old
    per-account workflow used, just keyed by division instead of account."""
    divisions = _division_options(db)
    rows = []
    for d in divisions:
        last = (
            db.query(models.DivisionReceivableDaily)
            .filter(
                models.DivisionReceivableDaily.division_id == d.id,
                models.DivisionReceivableDaily.position_date <= position_date,
            )
            .order_by(models.DivisionReceivableDaily.position_date.desc())
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
def save_division_positions(
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
            db.query(models.DivisionReceivableDaily)
            .filter(
                models.DivisionReceivableDaily.position_date == payload.position_date,
                models.DivisionReceivableDaily.division_id == row.division_id,
            )
            .first()
        )
        if existing:
            existing.amount = row.amount
        else:
            db.add(
                models.DivisionReceivableDaily(
                    position_date=payload.position_date,
                    division_id=row.division_id,
                    amount=row.amount,
                )
            )
    db.commit()
    return {"saved": len(payload.rows), "position_date": payload.position_date}


@router.get("/divisions/table", response_model=list[schemas.DivisionReceivableTableRow])
def division_table(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    """The full Date x Division history, most recent first. Only actual
    recorded entries appear (no carry-forward fill -- see
    DivisionReceivableTableRow's docstring): a division with nothing saved
    for a given date simply has no key in that row's `amounts`."""
    q = db.query(models.DivisionReceivableDaily)
    if start:
        q = q.filter(models.DivisionReceivableDaily.position_date >= start)
    if end:
        q = q.filter(models.DivisionReceivableDaily.position_date <= end)
    entries = q.order_by(models.DivisionReceivableDaily.position_date.desc()).all()

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
