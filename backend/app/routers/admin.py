from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import require_manager
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ResetDataRequest(BaseModel):
    scope: str  # "transactions" | "accounts" | "everything"
    confirm: bool = False


@router.post("/reset-data")
def reset_data(
    payload: ResetDataRequest,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    """Wipes test data so you can move from testing to real figures without
    carrying test rows forward. Three scopes:

    - 'transactions': clears Bank Dues, Receivables, and FX Rates only.
      Business Units, Divisions, Banks, Master Accounts, Currencies and
      Users are left alone -- use this once your account/currency setup is
      right and you just want to clear out test transaction data.
    - 'accounts' (Round 12): clears Bank Dues, account-linked Receivables,
      and Master Accounts -- for when the accounts themselves (e.g. their
      Account Numbers) were set up wrong and can't just be edited because
      Bank Dues/Receivables history is already linked to them. Business
      Units, Divisions, Banks, Currencies, Division Receivables, and FX
      Rates are left alone -- re-add accounts fresh afterward via Settings
      > Accounts or a Bank Dues import (which auto-creates them).
    - 'everything': also clears Master Accounts, Divisions, Business
      Units, and Banks (but never Users or Currencies, since those are
      awkward to lose entirely) -- use this for a full clean slate.

    Requires confirm=true -- this is deliberately not a one-click action.
    Round 12: removed from the Settings UI at the user's request (kept
    here so it's still reachable directly, e.g. via curl, when needed) --
    see the project doc for the exact call.
    """
    if payload.scope not in ("transactions", "accounts", "everything"):
        raise HTTPException(400, "scope must be 'transactions', 'accounts', or 'everything'.")
    if not payload.confirm:
        raise HTTPException(400, "Set confirm=true to actually run this -- it deletes data.")

    counts = {}
    # Bank Dues and account-linked Receivables are cleared for every scope
    # -- they're always transaction data tied to an account.
    counts["bank_dues"] = db.query(models.BankDue).delete()
    counts["receivables_daily"] = db.query(models.ReceivableDaily).delete()

    if payload.scope in ("transactions", "everything"):
        # FX Rates aren't account-linked at all, so 'accounts' deliberately
        # leaves them alone -- only 'transactions' and 'everything' clear them.
        counts["fx_rates"] = db.query(models.FxRate).delete()

    if payload.scope in ("accounts", "everything"):
        counts["master_accounts"] = db.query(models.MasterAccount).delete()

    if payload.scope == "everything":
        counts["divisions"] = db.query(models.Division).delete()
        counts["business_units"] = db.query(models.BusinessUnit).delete()
        counts["banks"] = db.query(models.Bank).delete()
        counts["currency_pairs"] = db.query(models.CurrencyPair).delete()

    db.commit()
    return {"scope": payload.scope, "deleted": counts}
