from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import models
from ..auth import get_current_user
from ..database import get_db
from .home import _amount_in_sdg

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class CoverTrendPoint(BaseModel):
    position_date: date
    total_receivables_sdg: float
    total_dues_sdg: float
    gap_sdg: float


@router.get("/cover-trend", response_model=list[CoverTrendPoint])
def cover_trend(
    start: date = Query(...),
    end: date = Query(...),
    business_unit_id: int | None = None,
    division_id: int | None = None,
    bank_id: int | None = None,
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    """Dues aren't logged as a daily time series (only their current
    status is tracked), so the 'dues' side of this trend is the current
    total active dues held constant across the window -- what moves day to
    day is the receivables side, which IS a real daily snapshot. This still
    answers the question users care about: how has our cover position
    trended as receivables came in, against where dues currently stand."""
    q = db.query(models.MasterAccount)
    if business_unit_id:
        q = q.filter(models.MasterAccount.business_unit_id == business_unit_id)
    if division_id:
        q = q.filter(models.MasterAccount.division_id == division_id)
    if bank_id:
        q = q.filter(models.MasterAccount.bank_id == bank_id)
    accounts = q.all()
    account_ids = [a.id for a in accounts]
    acct_by_id = {a.id: a for a in accounts}

    total_dues = 0.0
    if account_ids:
        due_rows = (
            db.query(models.BankDue)
            .filter(models.BankDue.account_id.in_(account_ids), models.BankDue.status == "Active")
            .all()
        )
        for d in due_rows:
            acct = acct_by_id.get(d.account_id)
            if not acct:
                continue
            amt, ok = _amount_in_sdg(db, d.amount, acct.currency)
            if ok:
                total_dues += float(amt)

    points: list[CoverTrendPoint] = []
    if account_ids:
        recv_rows = (
            db.query(models.ReceivableDaily)
            .filter(
                models.ReceivableDaily.account_id.in_(account_ids),
                models.ReceivableDaily.position_date >= start,
                models.ReceivableDaily.position_date <= end,
            )
            .order_by(models.ReceivableDaily.position_date)
            .all()
        )
        by_date: dict[date, float] = {}
        for r in recv_rows:
            acct = acct_by_id.get(r.account_id)
            if not acct:
                continue
            amt, ok = _amount_in_sdg(db, r.amount, acct.currency)
            if ok:
                by_date[r.position_date] = by_date.get(r.position_date, 0.0) + float(amt)
        for d in sorted(by_date.keys()):
            recv = by_date[d]
            points.append(
                CoverTrendPoint(
                    position_date=d,
                    total_receivables_sdg=recv,
                    total_dues_sdg=total_dues,
                    # dues - receivables: positive/"covered" when dues cover
                    # receivables, negative when receivables exceed dues
                    # (uncovered exposure) -- same convention as home.py.
                    gap_sdg=total_dues - recv,
                )
            )
    return points
