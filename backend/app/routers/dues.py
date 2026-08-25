from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..database import get_db
from ..export_utils import xlsx_response

router = APIRouter(prefix="/api/dues", tags=["dues"])


@router.get("", response_model=list[schemas.BankDueOut])
def list_dues(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.BankDue).order_by(models.BankDue.due_date).all()


@router.get("/export")
def export_dues(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    dues = (
        db.query(models.BankDue)
        .options(joinedload(models.BankDue.account))
        .order_by(models.BankDue.due_date)
        .all()
    )
    rows = [
        {
            "Account": f"{d.account.bank.short_name} - {d.account.account_number}" if d.account else "",
            "Due Date": d.due_date,
            "Facility Type": d.facility_type,
            "Amount": float(d.amount) if d.amount is not None else None,
            "Status": d.status,
        }
        for d in dues
    ]
    return xlsx_response(rows, "bank_dues.xlsx")


@router.post("", response_model=schemas.BankDueOut)
def create_due(
    payload: schemas.BankDueCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    due = models.BankDue(**payload.model_dump(), status="Active")
    db.add(due)
    db.commit()
    db.refresh(due)
    return due


@router.post("/{due_id}/settle", response_model=schemas.BankDueOut)
def settle_due(
    due_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_write)
):
    due = db.query(models.BankDue).get(due_id)
    if due:
        due.status = "Settled"
        db.commit()
        db.refresh(due)
    return due
