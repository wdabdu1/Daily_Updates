from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user, require_manager
from ..database import get_db
from ..export_utils import xlsx_response

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


def _to_out(a: models.MasterAccount) -> schemas.MasterAccountOut:
    return schemas.MasterAccountOut(
        id=a.id,
        business_unit_id=a.business_unit_id,
        division_id=a.division_id,
        bank_id=a.bank_id,
        account_name=a.account_name,
        account_number=a.account_number,
        currency=a.currency,
        business_unit_name=a.business_unit.name if a.business_unit else None,
        division_name=a.division.name if a.division else None,
        bank_short_name=a.bank.short_name if a.bank else None,
    )


@router.get("", response_model=list[schemas.MasterAccountOut])
def list_accounts(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    accounts = (
        db.query(models.MasterAccount)
        .options(
            joinedload(models.MasterAccount.business_unit),
            joinedload(models.MasterAccount.division),
            joinedload(models.MasterAccount.bank),
        )
        .all()
    )
    return [_to_out(a) for a in accounts]


@router.post("", response_model=schemas.MasterAccountOut)
def create_account(
    payload: schemas.MasterAccountCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    division = db.query(models.Division).get(payload.division_id)
    if not division or division.business_unit_id != payload.business_unit_id:
        raise HTTPException(400, "This division does not belong to the selected business unit.")
    if not db.query(models.Bank).get(payload.bank_id):
        raise HTTPException(400, "Unknown bank.")
    if not db.query(models.Currency).get(payload.currency):
        raise HTTPException(400, "Unknown currency.")

    account = models.MasterAccount(**payload.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return _to_out(account)


@router.get("/export")
def export_accounts(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    accounts = (
        db.query(models.MasterAccount)
        .options(
            joinedload(models.MasterAccount.business_unit),
            joinedload(models.MasterAccount.division),
            joinedload(models.MasterAccount.bank),
        )
        .all()
    )
    rows = [
        {
            "Business Unit": a.business_unit.name if a.business_unit else "",
            "Division": a.division.name if a.division else "",
            "Bank": a.bank.short_name if a.bank else "",
            "Account Name": a.account_name,
            "Account Number": a.account_number,
            "Currency": a.currency,
        }
        for a in accounts
    ]
    return xlsx_response(rows, "master_accounts.xlsx")
