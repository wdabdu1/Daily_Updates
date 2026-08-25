from datetime import date, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends
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


@router.get("/form", response_model=list[ReceivableFormRow])
def get_form(db: Session = Depends(get_db), _u: models.User = Depends(require_write)):
    """Powers the 'Start Update' workflow: every account, pre-filled with
    the most recent prior snapshot amount (typically yesterday's)."""
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
            .filter(models.ReceivableDaily.account_id == a.id)
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
