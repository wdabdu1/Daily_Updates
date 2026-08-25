from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import require_any
from ..database import get_db
from ..rates import get_latest_rate

router = APIRouter(prefix="/api/home", tags=["home"])


def _amount_in_sdg(db: Session, amount: Decimal, currency: str) -> tuple[Optional[Decimal], bool]:
    """Returns (amount_in_sdg, converted_ok). If currency is already SDG,
    no conversion is needed. Otherwise looks up the latest Market rate for
    CURRENCY/SDG; if none exists yet, the amount can't be safely included
    and converted_ok is False."""
    if currency == "SDG":
        return amount, True
    rate, _ = get_latest_rate(db, currency, "SDG", "Market")
    if rate is None:
        return None, False
    return amount * rate, True


def _latest_snapshot_date(db: Session):
    return db.query(func.max(models.ReceivableDaily.position_date)).scalar()


def _compute_group(db: Session, accounts: list[models.MasterAccount], as_of):
    """Sums receivables (as of the given snapshot date) and active dues for
    a specific list of accounts, normalizing every amount to SDG."""
    total_recv = Decimal("0")
    total_dues = Decimal("0")
    unconverted = 0

    account_ids = [a.id for a in accounts]
    if not account_ids:
        return total_recv, total_dues, unconverted

    if as_of:
        recv_rows = (
            db.query(models.ReceivableDaily)
            .filter(
                models.ReceivableDaily.position_date == as_of,
                models.ReceivableDaily.account_id.in_(account_ids),
            )
            .all()
        )
        acct_by_id = {a.id: a for a in accounts}
        for r in recv_rows:
            acct = acct_by_id.get(r.account_id)
            if not acct:
                continue
            amt, ok = _amount_in_sdg(db, r.amount, acct.currency)
            if ok:
                total_recv += amt
            else:
                unconverted += 1

    due_rows = (
        db.query(models.BankDue)
        .filter(models.BankDue.account_id.in_(account_ids), models.BankDue.status == "Active")
        .all()
    )
    acct_by_id = {a.id: a for a in accounts}
    for d in due_rows:
        acct = acct_by_id.get(d.account_id)
        if not acct:
            continue
        amt, ok = _amount_in_sdg(db, d.amount, acct.currency)
        if ok:
            total_dues += amt
        else:
            unconverted += 1

    return total_recv, total_dues, unconverted


@router.get("/summary", response_model=schemas.HomeSummary)
def summary(db: Session = Depends(get_db), _user: models.User = Depends(require_any)):
    as_of = _latest_snapshot_date(db)
    accounts = db.query(models.MasterAccount).all()
    total_recv, total_dues, unconverted = _compute_group(db, accounts, as_of)

    gap = total_recv - total_dues
    gap_pct = None
    if total_dues != 0:
        gap_pct = (gap / total_dues * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    usd_rate, usd_rate_date = get_latest_rate(db, "USD", "SDG", "Market")
    gap_usd = None
    if usd_rate:
        gap_usd = (gap / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    if not accounts:
        status_ = "no_data"
        notes = "No accounts registered yet -- add accounts in Settings to start tracking."
    elif as_of is None:
        status_ = "no_data"
        notes = "No receivables have been entered yet -- use Bank Dues > Update Today's Receivables."
    else:
        status_ = "covered" if gap >= 0 else "shortfall"
        notes = None

    if unconverted:
        extra = (
            f"{unconverted} entr(y/ies) in a currency with no SDG rate yet were excluded"
            " from these totals."
        )
        notes = f"{notes} {extra}" if notes else extra

    return schemas.HomeSummary(
        as_of=as_of,
        total_receivables_sdg=total_recv,
        total_dues_sdg=total_dues,
        gap_sdg=gap,
        gap_pct=gap_pct,
        usd_sdg_rate=usd_rate,
        usd_sdg_rate_date=usd_rate_date,
        gap_usd_equivalent=gap_usd,
        status=status_,
        unconverted_account_count=unconverted,
        notes=notes,
    )


@router.get("/breakdown", response_model=list[schemas.CoverBreakdownRow])
def breakdown(
    group_by: str = Query("business_unit", pattern="^(business_unit|division|bank)$"),
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_any),
):
    """Powers the Cover Analysis drill-down: same gap logic as /summary but
    grouped by BU, Division, or Bank so cross-subsidy between units is
    visible."""
    as_of = _latest_snapshot_date(db)
    accounts = db.query(models.MasterAccount).all()

    groups: dict[str, list[models.MasterAccount]] = {}
    for a in accounts:
        if group_by == "business_unit":
            label = a.business_unit.name if a.business_unit else "Unassigned"
        elif group_by == "division":
            label = a.division.name if a.division else "Unassigned"
        else:
            label = a.bank.short_name if a.bank else "Unassigned"
        groups.setdefault(label, []).append(a)

    rows = []
    for label, group_accounts in sorted(groups.items()):
        total_recv, total_dues, _unconv = _compute_group(db, group_accounts, as_of)
        gap = total_recv - total_dues
        rows.append(
            schemas.CoverBreakdownRow(
                group_label=label,
                total_receivables_sdg=total_recv,
                total_dues_sdg=total_dues,
                gap_sdg=gap,
                status="covered" if gap >= 0 else "shortfall",
            )
        )
    return rows
