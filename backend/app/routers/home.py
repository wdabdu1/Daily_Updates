from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

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


def _latest_receivables_date(db: Session):
    return db.query(func.max(models.DivisionReceivableDaily.position_date)).scalar()


def _latest_cash_date(db: Session):
    return db.query(func.max(models.DivisionCashBalanceDaily.position_date)).scalar()


def _cover_pct(dues: Decimal, receivables: Decimal) -> Optional[Decimal]:
    """Round 14: 'Cover %' = Active Dues / Receivables x 100 -- same literal
    formula as analysis.py's cover-snapshot Cover %, kept as its own small
    helper here rather than imported to avoid a cross-router dependency for
    one four-line function. None (not a fabricated 0%/inf) on a zero
    denominator."""
    if receivables == 0:
        return None
    return (dues / receivables * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dues_in_sdg(db: Session, accounts: list[models.MasterAccount]) -> tuple[Decimal, int]:
    """Sums active dues (converted to SDG) for a specific list of accounts.
    Returns (total, unconverted_count)."""
    total = Decimal("0")
    unconverted = 0
    account_ids = [a.id for a in accounts]
    if not account_ids:
        return total, unconverted
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
            total += amt
        else:
            unconverted += 1
    return total, unconverted


FX_SNAPSHOT_RATE_TYPES = ["Market", "CBOS", "Pricing"]


def _fx_snapshot(db: Session) -> list[schemas.FxSnapshotRate]:
    """Today's (latest-known, carry-forward) USD/SDG and AED/SDG rate for
    each rate type, for the Home page's FX cards. A rate type is included
    as long as at least one side has a figure on file -- the other side
    renders as absent rather than dropping the whole card."""
    rows = []
    for rate_type in FX_SNAPSHOT_RATE_TYPES:
        usd_rate, usd_date = get_latest_rate(db, "USD", "SDG", rate_type)
        aed_rate, aed_date = get_latest_rate(db, "AED", "SDG", rate_type)
        if usd_rate is None and aed_rate is None:
            continue
        rows.append(
            schemas.FxSnapshotRate(
                rate_type=rate_type,
                usd_rate=usd_rate,
                usd_rate_date=usd_date,
                aed_rate=aed_rate,
                aed_rate_date=aed_date,
            )
        )
    return rows


def _receivables_by_division(db: Session, as_of) -> dict[int, Decimal]:
    """Every division's recorded position on `as_of` (already SDG, no
    conversion needed -- see DivisionReceivableDaily). Empty dict if no
    receivables have been recorded for that date."""
    if not as_of:
        return {}
    rows = (
        db.query(models.DivisionReceivableDaily)
        .filter(models.DivisionReceivableDaily.position_date == as_of)
        .all()
    )
    return {r.division_id: r.amount for r in rows}


def _cash_by_division(db: Session, as_of) -> dict[int, Decimal]:
    """Same as _receivables_by_division above, but for Cash Balances
    (DivisionCashBalanceDaily) -- Round 14."""
    if not as_of:
        return {}
    rows = (
        db.query(models.DivisionCashBalanceDaily)
        .filter(models.DivisionCashBalanceDaily.position_date == as_of)
        .all()
    )
    return {r.division_id: r.amount for r in rows}


@router.get("/summary", response_model=schemas.HomeSummary)
def summary(db: Session = Depends(get_db), _user: models.User = Depends(require_any)):
    accounts = db.query(models.MasterAccount).all()
    divisions = db.query(models.Division).all()

    # Round 14: the page's single "as of" date is the later of Credit Sales
    # (PDC) and Cash Balances' own latest recorded date -- same convention
    # already established by analysis.py's Round 13 "Overall Cover Analysis"
    # (PDC + Cash combined), so a cash-only day is still picked up rather
    # than silently ignored because PDC wasn't touched that same day.
    recv_date = _latest_receivables_date(db)
    cash_date = _latest_cash_date(db)
    candidate_dates = [d for d in (recv_date, cash_date) if d is not None]
    as_of = max(candidate_dates) if candidate_dates else None

    recv_by_division = _receivables_by_division(db, as_of)
    cash_by_division = _cash_by_division(db, as_of)
    total_recv = sum(recv_by_division.values(), Decimal("0"))  # PDC only -- "exc. Cash"
    total_cash = sum(cash_by_division.values(), Decimal("0"))
    total_recv_inc_cash = total_recv + total_cash
    total_dues, unconverted = _dues_in_sdg(db, accounts)

    # Cover convention: Dues are the hedge/coverage side, Receivables are the
    # exposure they need to cover. gap = dues - receivables, so gap >= 0
    # ("covered") means dues cover (or exceed) receivables -- positive/green.
    # gap < 0 ("shortfall") means receivables exceed dues -- an uncovered
    # exposure, shown red. The page's headline status/alert stays keyed off
    # the "exc. Cash" gap (unchanged from before Round 14) -- Round 14 only
    # added the "inc. Cash" figures as a second, parallel set of stat cards.
    gap = total_dues - total_recv
    gap_inc_cash = total_dues - total_recv_inc_cash
    gap_pct = None
    if total_dues != 0:
        gap_pct = (gap / total_dues * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    cover_pct_exc_cash = _cover_pct(total_dues, total_recv)
    cover_pct_inc_cash = _cover_pct(total_dues, total_recv_inc_cash)

    usd_rate, usd_rate_date = get_latest_rate(db, "USD", "SDG", "Market")
    gap_usd = None
    gap_inc_cash_usd = None
    total_recv_usd = None
    total_recv_inc_cash_usd = None
    total_cash_usd = None
    total_dues_usd = None
    if usd_rate:
        gap_usd = (gap / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        gap_inc_cash_usd = (gap_inc_cash / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_recv_usd = (total_recv / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_recv_inc_cash_usd = (total_recv_inc_cash / usd_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_cash_usd = (total_cash / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        total_dues_usd = (total_dues / usd_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    eur_usd_rate, eur_usd_rate_date = get_latest_rate(db, "EUR", "USD", "Market")

    if not accounts and not divisions:
        status_ = "no_data"
        notes = "No accounts or divisions registered yet -- set them up in Settings to start tracking."
    elif as_of is None:
        status_ = "no_data"
        notes = "No receivables have been entered yet -- use Bank Dues > Today's Update."
    else:
        status_ = "covered" if gap >= 0 else "shortfall"
        notes = None

    if unconverted:
        extra = (
            f"{unconverted} due(s) in a currency with no SDG rate yet were excluded"
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
        total_receivables_usd=total_recv_usd,
        total_dues_usd=total_dues_usd,
        status=status_,
        unconverted_account_count=unconverted,
        notes=notes,
        fx_snapshot=_fx_snapshot(db),
        total_cash_sdg=total_cash,
        total_cash_usd=total_cash_usd,
        total_receivables_inc_cash_sdg=total_recv_inc_cash,
        total_receivables_inc_cash_usd=total_recv_inc_cash_usd,
        gap_inc_cash_sdg=gap_inc_cash,
        gap_inc_cash_usd_equivalent=gap_inc_cash_usd,
        cover_pct_inc_cash=cover_pct_inc_cash,
        cover_pct_exc_cash=cover_pct_exc_cash,
        eur_usd_rate=eur_usd_rate,
        eur_usd_rate_date=eur_usd_rate_date,
    )


@router.get("/breakdown", response_model=schemas.CoverBreakdownResponse)
def breakdown(
    group_by: str = Query("business_unit", pattern="^(business_unit|division|bank)$"),
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_any),
):
    """Powers the Home 'Cover by' breakdown. Dues are always groupable by
    Business Unit, Division or Bank (via the owning account). Receivables
    are now recorded per Division (see DivisionReceivableDaily) with no
    bank concept at all -- grouping "by Bank" is Dues-only, and each row's
    total_receivables_sdg/gap_sdg/status come back None so the UI can show
    a dash instead of implying a real $0. Business Unit rolls up its
    divisions' receivables."""
    as_of = _latest_receivables_date(db)
    accounts = (
        db.query(models.MasterAccount)
        .options(
            joinedload(models.MasterAccount.business_unit),
            joinedload(models.MasterAccount.division),
            joinedload(models.MasterAccount.bank),
        )
        .all()
    )
    divisions = (
        db.query(models.Division).options(joinedload(models.Division.business_unit)).all()
    )
    recv_by_division_id = _receivables_by_division(db, as_of)

    receivables_applicable = group_by != "bank"

    # ---- Dues, grouped by the requested dimension -------------------------
    due_groups: dict[str, list[models.MasterAccount]] = {}
    for a in accounts:
        if group_by == "business_unit":
            label = a.business_unit.name if a.business_unit else "Unassigned"
        elif group_by == "division":
            label = a.division.name if a.division else "Unassigned"
        else:
            label = a.bank.short_name if a.bank else "Unassigned"
        due_groups.setdefault(label, []).append(a)

    dues_by_label: dict[str, Decimal] = {}
    for label, group_accounts in due_groups.items():
        total_dues, _unconv = _dues_in_sdg(db, group_accounts)
        dues_by_label[label] = total_dues

    # ---- Receivables, grouped the same way (bank grouping: skipped) -------
    recv_by_label: dict[str, Decimal] = {}
    if group_by == "division":
        for d in divisions:
            recv_by_label[d.name] = recv_by_label.get(d.name, Decimal("0")) + recv_by_division_id.get(
                d.id, Decimal("0")
            )
    elif group_by == "business_unit":
        for d in divisions:
            bu_label = d.business_unit.name if d.business_unit else "Unassigned"
            recv_by_label[bu_label] = recv_by_label.get(bu_label, Decimal("0")) + recv_by_division_id.get(
                d.id, Decimal("0")
            )

    all_labels = sorted(set(dues_by_label) | set(recv_by_label))
    grand_total_recv = sum(recv_by_label.values(), Decimal("0"))
    grand_total_dues = sum(dues_by_label.values(), Decimal("0"))

    rows = []
    for label in all_labels:
        total_dues = dues_by_label.get(label, Decimal("0"))
        if not receivables_applicable:
            rows.append(
                schemas.CoverBreakdownRow(
                    group_label=label,
                    total_receivables_sdg=None,
                    total_dues_sdg=total_dues,
                    gap_sdg=None,
                    status=None,
                    pct_of_total_receivables=None,
                )
            )
            continue
        total_recv = recv_by_label.get(label, Decimal("0"))
        gap = total_dues - total_recv
        pct = None
        if grand_total_recv != 0:
            pct = (total_recv / grand_total_recv * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append(
            schemas.CoverBreakdownRow(
                group_label=label,
                total_receivables_sdg=total_recv,
                total_dues_sdg=total_dues,
                gap_sdg=gap,
                status="covered" if gap >= 0 else "shortfall",
                pct_of_total_receivables=pct,
            )
        )

    if receivables_applicable:
        grand_gap = grand_total_dues - grand_total_recv
        total_row = schemas.CoverBreakdownRow(
            group_label="Total",
            total_receivables_sdg=grand_total_recv,
            total_dues_sdg=grand_total_dues,
            gap_sdg=grand_gap,
            status="covered" if grand_gap >= 0 else "shortfall",
            pct_of_total_receivables=Decimal("100.00") if grand_total_recv else None,
        )
    else:
        total_row = schemas.CoverBreakdownRow(
            group_label="Total",
            total_receivables_sdg=None,
            total_dues_sdg=grand_total_dues,
            gap_sdg=None,
            status=None,
            pct_of_total_receivables=None,
        )

    return schemas.CoverBreakdownResponse(
        rows=rows, total=total_row, receivables_applicable=receivables_applicable
    )


@router.get("/receivables-contribution", response_model=schemas.ReceivablesContributionResponse)
def receivables_contribution(
    db: Session = Depends(get_db),
    _user: models.User = Depends(require_any),
):
    """Powers the Home 'Receivables Contribution' table -- always at
    division grain, with Business Unit AND Division shown as separate
    columns (Round 13) rather than a toggle between the two. Dues on an
    account with no division link land in a trailing 'Unassigned' row
    rather than being silently dropped."""
    as_of = _latest_receivables_date(db)
    divisions = (
        db.query(models.Division)
        .options(joinedload(models.Division.business_unit))
        .all()
    )
    recv_by_division_id = _receivables_by_division(db, as_of)
    accounts = (
        db.query(models.MasterAccount)
        .options(joinedload(models.MasterAccount.division))
        .all()
    )

    div_accounts: dict[int, list[models.MasterAccount]] = {}
    unassigned_accounts: list[models.MasterAccount] = []
    for a in accounts:
        if a.division_id is not None:
            div_accounts.setdefault(a.division_id, []).append(a)
        else:
            unassigned_accounts.append(a)

    dues_by_division_id: dict[int, Decimal] = {}
    for div_id, group_accounts in div_accounts.items():
        total_dues, _unconv = _dues_in_sdg(db, group_accounts)
        dues_by_division_id[div_id] = total_dues

    unassigned_dues = Decimal("0")
    if unassigned_accounts:
        unassigned_dues, _unconv = _dues_in_sdg(db, unassigned_accounts)

    grand_total_recv = sum(recv_by_division_id.values(), Decimal("0"))

    sorted_divisions = sorted(
        divisions,
        key=lambda d: ((d.business_unit.name if d.business_unit else "Unassigned"), d.name),
    )

    rows = []
    for d in sorted_divisions:
        total_recv = recv_by_division_id.get(d.id, Decimal("0"))
        total_dues = dues_by_division_id.get(d.id, Decimal("0"))
        pct = None
        if grand_total_recv != 0:
            pct = (total_recv / grand_total_recv * 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        rows.append(
            schemas.ReceivablesContributionRow(
                business_unit_name=d.business_unit.name if d.business_unit else "Unassigned",
                division_name=d.name,
                total_receivables_sdg=total_recv,
                pct_of_total_receivables=pct,
                total_dues_sdg=total_dues,
            )
        )

    if unassigned_accounts:
        rows.append(
            schemas.ReceivablesContributionRow(
                business_unit_name="Unassigned",
                division_name=None,
                total_receivables_sdg=Decimal("0"),
                pct_of_total_receivables=None,
                total_dues_sdg=unassigned_dues,
            )
        )

    total_row = schemas.ReceivablesContributionRow(
        business_unit_name="Total",
        division_name=None,
        total_receivables_sdg=grand_total_recv,
        pct_of_total_receivables=Decimal("100.00") if grand_total_recv else None,
        total_dues_sdg=sum(dues_by_division_id.values(), Decimal("0")) + unassigned_dues,
    )
    return schemas.ReceivablesContributionResponse(rows=rows, total=total_row)
