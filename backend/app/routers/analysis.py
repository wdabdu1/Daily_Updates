from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
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


# ---------------------------------------------------------------------------
# Round 11: cover-snapshot. Replaces cover-trend as what Cover Analysis's
# chart actually renders -- a single day's Receivables (stacked by
# Division) vs Dues (stacked by Bank) vs the Gap, as three bars, rather
# than a date-range line. cover_trend above is left in place (same
# "kept, not deleted" convention as the legacy per-account receivables
# endpoints) but nothing in the UI calls it anymore.
# ---------------------------------------------------------------------------

# Categorical palette, slots 1-8, per the dataviz skill's validated default
# order (fixed order, never cycled -- see palette.md). A group with more
# than 8 distinct labels folds everything past the 8th into a trailing
# "Other" slice using the muted-ink color rather than reusing/cycling a hue.
CATEGORICAL_PALETTE = [
    "#2a78d6",  # 1 blue
    "#eb6834",  # 2 orange
    "#1baf7a",  # 3 aqua
    "#eda100",  # 4 yellow
    "#e87ba4",  # 5 magenta
    "#008300",  # 6 green
    "#4a3aa7",  # 7 violet
    "#e34948",  # 8 red
]
OTHER_SLICE_COLOR = "#898781"  # muted ink -- for the folded "Other" slice only


def _assign_slice_colors(amounts_by_label: dict[str, Decimal]) -> list[schemas.CoverSnapshotSlice]:
    """Turns a {label: amount} map into colored, stacking-ready slices.
    Sorted alphabetically so a given label always lands in the same palette
    slot from one request to the next (stable colors as long as the same
    labels are present) -- amounts are never used for ordering, since color
    must follow entity identity, not rank."""
    labels = sorted(amounts_by_label.keys())
    slices = []
    other_total = Decimal("0")
    for i, label in enumerate(labels):
        amount = amounts_by_label[label]
        if i < len(CATEGORICAL_PALETTE):
            slices.append(
                schemas.CoverSnapshotSlice(label=label, amount=amount, color=CATEGORICAL_PALETTE[i])
            )
        else:
            other_total += amount
    if other_total:
        slices.append(
            schemas.CoverSnapshotSlice(label="Other", amount=other_total, color=OTHER_SLICE_COLOR)
        )
    return slices


@router.get("/cover-snapshot", response_model=schemas.CoverSnapshot)
def cover_snapshot(
    position_date: date | None = Query(
        None, description="Defaults to the latest date with recorded division receivables."
    ),
    db: Session = Depends(get_db),
    _u: models.User = Depends(get_current_user),
):
    """Powers the Cover Analysis stacked-bar snapshot: one day's Receivables
    (stacked by Division) next to Dues (stacked by Bank) next to the Gap.
    Receivables and Dues are fundamentally different populations here --
    receivables have no bank concept (see DivisionReceivableDaily) and dues
    have no division concept unless traced through their account -- so this
    endpoint reports each side by its own natural dimension rather than
    forcing a shared one."""
    as_of = position_date or db.query(
        func.max(models.DivisionReceivableDaily.position_date)
    ).scalar()

    recv_by_division: dict[str, Decimal] = {}
    if as_of:
        rows = (
            db.query(models.DivisionReceivableDaily)
            .options(joinedload(models.DivisionReceivableDaily.division))
            .filter(models.DivisionReceivableDaily.position_date == as_of)
            .all()
        )
        for r in rows:
            label = r.division.name if r.division else "Unassigned"
            recv_by_division[label] = recv_by_division.get(label, Decimal("0")) + r.amount

    accounts = (
        db.query(models.MasterAccount).options(joinedload(models.MasterAccount.bank)).all()
    )
    acct_by_id = {a.id: a for a in accounts}
    due_rows = db.query(models.BankDue).filter(models.BankDue.status == "Active").all()

    dues_by_bank: dict[str, Decimal] = {}
    for d in due_rows:
        acct = acct_by_id.get(d.account_id)
        if not acct:
            continue
        amt, ok = _amount_in_sdg(db, d.amount, acct.currency)
        if not ok:
            continue
        label = acct.bank.short_name if acct.bank else "Unassigned"
        dues_by_bank[label] = dues_by_bank.get(label, Decimal("0")) + amt

    total_recv = sum(recv_by_division.values(), Decimal("0"))
    total_dues = sum(dues_by_bank.values(), Decimal("0"))

    return schemas.CoverSnapshot(
        position_date=as_of,
        receivables_by_division=_assign_slice_colors(recv_by_division),
        dues_by_bank=_assign_slice_colors(dues_by_bank),
        total_receivables_sdg=total_recv,
        total_dues_sdg=total_dues,
        gap_sdg=total_dues - total_recv,
    )
