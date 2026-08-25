from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_manager
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetDataRequest(BaseModel):
    scope: str  # "transactions" | "everything"
    confirm: bool = False


@router.post("/reset-data")
def reset_data(
    payload: ResetDataRequest,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    """Wipes test data so you can move from testing to real figures without
    carrying test rows forward. Two scopes:

    - 'transactions': clears Bank Dues, Receivables, and FX Rates only.
      Business Units, Divisions, Banks, Master Accounts, Currencies and
      Users are left alone -- use this once your account/currency setup is
      right and you just want to clear out test transaction data.
    - 'everything': also clears Master Accounts, Divisions, Business
      Units, and Banks (but never Users or Currencies, since those are
      awkward to lose entirely) -- use this for a full clean slate.

    Requires confirm=true -- this is deliberately not a one-click action.
    """
    if payload.scope not in ("transactions", "everything"):
        raise HTTPException(400, "scope must be 'transactions' or 'everything'.")
    if not payload.confirm:
        raise HTTPException(400, "Set confirm=true to actually run this -- it deletes data.")

    counts = {}
    counts["bank_dues"] = db.query(models.BankDue).delete()
    counts["receivables_daily"] = db.query(models.ReceivableDaily).delete()
    counts["fx_rates"] = db.query(models.FxRate).delete()

    if payload.scope == "everything":
        counts["master_accounts"] = db.query(models.MasterAccount).delete()
        counts["divisions"] = db.query(models.Division).delete()
        counts["business_units"] = db.query(models.BusinessUnit).delete()
        counts["banks"] = db.query(models.Bank).delete()
        counts["currency_pairs"] = db.query(models.CurrencyPair).delete()

    db.commit()
    return {"scope": payload.scope, "deleted": counts}
