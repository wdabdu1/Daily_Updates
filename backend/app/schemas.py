from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: str
    display_name: Optional[str] = None
    email: Optional[str] = None


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "ReadWrite"
    display_name: Optional[str] = None
    email: Optional[str] = None


class UserUpdate(BaseModel):
    username: str
    role: str
    display_name: Optional[str] = None
    email: Optional[str] = None


class MeUpdateRequest(BaseModel):
    """Self-service profile edit -- deliberately smaller than UserUpdate:
    no username or role here, since those stay Manager-only via Settings >
    Users. Anyone logged in can rename themselves and set/change their own
    email regardless of role."""

    display_name: Optional[str] = None
    email: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class BusinessUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BusinessUnitCreate(BaseModel):
    name: str


class BusinessUnitUpdate(BaseModel):
    name: str


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    business_unit_id: int


class DivisionCreate(BaseModel):
    name: str
    business_unit_id: int


class DivisionUpdate(BaseModel):
    name: str
    business_unit_id: int


class BankOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    short_name: str
    full_name: str


class BankCreate(BaseModel):
    short_name: str
    full_name: str


class BankUpdate(BaseModel):
    short_name: str
    full_name: str


class CurrencyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code: str


class CurrencyCreate(BaseModel):
    code: str


class CurrencyPairOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    base_currency: str
    quote_currency: str
    supports_extended_rates: bool
    is_default: bool


class CurrencyPairCreate(BaseModel):
    base_currency: str
    quote_currency: str


class MasterAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    business_unit_id: Optional[int] = None
    division_id: Optional[int] = None
    bank_id: int
    account_name: str
    account_number: str
    currency: str
    business_unit_name: Optional[str] = None
    division_name: Optional[str] = None
    bank_short_name: Optional[str] = None


class MasterAccountCreate(BaseModel):
    # Optional: some Bank Dues data only reliably identifies the Bank/Account
    # -- Business Unit/Division attribution can be added later once
    # dedicated per-division dues data is available.
    business_unit_id: Optional[int] = None
    division_id: Optional[int] = None
    bank_id: int
    account_name: str
    account_number: str
    currency: str


class MasterAccountUpdate(BaseModel):
    business_unit_id: Optional[int] = None
    division_id: Optional[int] = None
    bank_id: int
    account_name: str
    account_number: str
    currency: str


class FxRateOut(BaseModel):
    # None for a carried-forward row (it's computed at query time, not a
    # real stored row) -- only present, and only then editable/deletable,
    # for a row that was actually entered.
    id: Optional[int] = None
    rate_date: date
    currency_pair: str
    rate_type: str
    rate: Decimal
    is_carried_forward: bool


class FxRateCreate(BaseModel):
    rate_date: date
    currency_pair_id: int
    rate_type: str
    rate: Decimal


class FxRateUpdate(BaseModel):
    rate: Decimal


class FxBatchRateCreate(BaseModel):
    """Market/CBOS/Pricing rates are always entered as one save covering
    USD, Euro and AED against SDG together -- all three are required, there
    is no partial batch save. Pydantic enforces "compulsory" here simply by
    these fields not being Optional."""

    rate_date: date
    rate_type: str
    usd_rate: Decimal
    euro_rate: Decimal
    aed_rate: Decimal


class FxBatchRateOut(BaseModel):
    rate_date: date
    rate_type: str
    usd: FxRateOut
    euro: FxRateOut
    aed: FxRateOut


class FxCombinedRow(BaseModel):
    """One calendar day's Market/CBOS/Pricing rates for a single selected
    currency (vs SDG), merged side by side. `*_id` is None for a
    carried-forward day (nothing stored for that exact date) or when that
    rate type has no entry at all yet -- only a non-None id is
    editable/deletable via the existing per-rate endpoints."""

    rate_date: date
    market_rate: Optional[Decimal] = None
    market_id: Optional[int] = None
    market_carried_forward: bool = False
    cbos_rate: Optional[Decimal] = None
    cbos_id: Optional[int] = None
    cbos_carried_forward: bool = False
    pricing_rate: Optional[Decimal] = None
    pricing_id: Optional[int] = None
    pricing_carried_forward: bool = False


class BankDueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    account_id: int
    due_date: Optional[date]
    facility_type: Optional[str]
    amount: Decimal
    status: str
    business_unit_name: Optional[str] = None
    division_name: Optional[str] = None
    bank_short_name: Optional[str] = None
    account_number: Optional[str] = None


class BankDueCreate(BaseModel):
    account_id: int
    due_date: date
    facility_type: str
    amount: Decimal


class BankDueUpdate(BaseModel):
    # Partial update -- only fields the caller actually sends are applied,
    # so an inline edit-row form can send just what changed (e.g. only
    # `amount`) instead of resubmitting every field.
    account_id: Optional[int] = None
    due_date: Optional[date] = None
    facility_type: Optional[str] = None
    amount: Optional[Decimal] = None
    status: Optional[str] = None


class ReceivableRow(BaseModel):
    account_id: int
    amount: Decimal


class ReceivableSaveRequest(BaseModel):
    position_date: date
    rows: list[ReceivableRow]


class DivisionOption(BaseModel):
    """A division as a receivables-table column / form row -- labeled with
    its Business Unit since Division names are only unique within a BU, not
    globally (two different BUs can each have a "Delta" division)."""

    id: int
    name: str
    business_unit_id: int
    business_unit_name: str


class DivisionReceivableFormRow(BaseModel):
    division_id: int
    division_name: str
    business_unit_name: str
    default_amount: Decimal
    default_amount_date: Optional[date] = None
    # True when default_amount_date == the requested position_date, i.e. an
    # entry for that exact day already exists and saving will UPDATE it
    # rather than fall back to an earlier day's figure as a starting point.
    is_recorded_for_date: bool


class DivisionReceivableRow(BaseModel):
    division_id: int
    amount: Decimal


class DivisionReceivableSaveRequest(BaseModel):
    position_date: date
    rows: list[DivisionReceivableRow]


class DivisionReceivableTableRow(BaseModel):
    position_date: date
    # Keyed by division id (as a string -- JSON object keys are always
    # strings), amount omitted/absent for a division with no entry on this
    # exact date (this table shows real recorded entries only, it does not
    # carry-forward fill every calendar day the way FX Rates does --
    # receivables snapshots are naturally episodic, not daily-guaranteed).
    amounts: dict[str, Decimal]
    total: Decimal


class FxSnapshotRate(BaseModel):
    """One rate-type's (Market/CBOS/Pricing) latest known USD/SDG rate, plus
    the equivalent AED/SDG rate for the same rate-type -- the Home page
    shows USD prominently and AED underneath in a smaller/greyer style.
    Either side (or both) can be None if that pair/rate-type has no entry
    on file yet -- the rate-type still renders, just without that figure.
    usd_rate_date and aed_rate_date can differ from each other (each is the
    latest entry for its own pair) so the frontend can show a per-figure
    "as of" if it ever needs to."""

    rate_type: str  # Market | CBOS | Pricing
    usd_rate: Optional[Decimal] = None
    usd_rate_date: Optional[date] = None
    aed_rate: Optional[Decimal] = None
    aed_rate_date: Optional[date] = None


class HomeSummary(BaseModel):
    as_of: Optional[date]
    total_receivables_sdg: Decimal
    total_dues_sdg: Decimal
    gap_sdg: Decimal
    gap_pct: Optional[Decimal]
    usd_sdg_rate: Optional[Decimal]
    usd_sdg_rate_date: Optional[date]
    gap_usd_equivalent: Optional[Decimal]
    # USD equivalents of the two top-line totals, using the same latest
    # USD/SDG Market rate as gap_usd_equivalent -- None when no rate is on
    # file yet (mirrors gap_usd_equivalent's own None case).
    total_receivables_usd: Optional[Decimal] = None
    total_dues_usd: Optional[Decimal] = None
    status: str  # "covered" | "shortfall" | "no_data"
    unconverted_account_count: int
    notes: Optional[str] = None
    # Today's FX snapshot cards: one row per rate-type that has at least a
    # USD or AED figure on file. Always in Market, CBOS, Pricing order.
    fx_snapshot: list[FxSnapshotRate] = []
    # Round 14: Home page's 2nd/3rd stat-card rows. total_receivables_sdg/usd
    # and gap_sdg/gap_usd_equivalent above stay PDC-only ("Receivables - exc.
    # Cash", unchanged from before Round 14); these add the Cash Balances
    # total and a parallel "inc. Cash" set of totals/gap/cover-%, plus each
    # flavor's Cover % (Active Dues / Receivables x 100, None on a zero
    # denominator -- same literal formula as analysis.py's Cover Analysis).
    total_cash_sdg: Decimal = Decimal("0")
    total_cash_usd: Optional[Decimal] = None
    total_receivables_inc_cash_sdg: Decimal = Decimal("0")
    total_receivables_inc_cash_usd: Optional[Decimal] = None
    gap_inc_cash_sdg: Decimal = Decimal("0")
    gap_inc_cash_usd_equivalent: Optional[Decimal] = None
    cover_pct_inc_cash: Optional[Decimal] = None
    cover_pct_exc_cash: Optional[Decimal] = None
    # Round 14: 4th FX snapshot card -- latest EUR/USD Market rate (an
    # International Rates pair, not one of the SDG-quote Market/CBOS/Pricing
    # rows in fx_snapshot above).
    eur_usd_rate: Optional[Decimal] = None
    eur_usd_rate_date: Optional[date] = None


class ImportRowError(BaseModel):
    row_number: int
    reason: str


class ImportResult(BaseModel):
    imported: int
    updated: int
    skipped: list[ImportRowError]


class CoverBreakdownRow(BaseModel):
    group_label: str
    # None (not zero) when this grouping dimension has no meaningful
    # receivables figure to show -- specifically, grouping "by Bank": Dues
    # are still bank-linked via their account, but receivables are now
    # recorded per Division with no bank concept at all, so there's nothing
    # real to sum for a bank row. Grouping by Division or Business Unit
    # always has a real figure (Business Unit is a roll-up of its
    # divisions' receivables). The frontend renders None as "—" and omits
    # the gap/status coloring for that row rather than implying a real $0.
    total_receivables_sdg: Optional[Decimal] = None
    total_dues_sdg: Decimal
    gap_sdg: Optional[Decimal] = None
    status: Optional[str] = None
    # Each group's receivables as a % of company-wide total receivables --
    # lets you see how much of the overall exposure a group represents even
    # when Dues can't yet be attributed the same way.
    pct_of_total_receivables: Optional[Decimal] = None


class CoverBreakdownResponse(BaseModel):
    rows: list[CoverBreakdownRow]
    # Company-wide totals for the same grouping dimension, so the UI can
    # render a "Total" row at the end without re-summing client-side.
    total: CoverBreakdownRow
    receivables_applicable: bool


class ReceivablesContributionRow(BaseModel):
    # Round 13: always carries both dimensions rather than a single
    # group_label toggled between them -- division_name is None only for
    # the trailing "Unassigned" row (dues on an account with no division
    # link) and for the "Total" row.
    business_unit_name: str
    division_name: Optional[str] = None
    total_receivables_sdg: Decimal
    pct_of_total_receivables: Optional[Decimal] = None
    total_dues_sdg: Decimal


class ReceivablesContributionResponse(BaseModel):
    rows: list[ReceivablesContributionRow]
    total: ReceivablesContributionRow


class CoverSnapshotSlice(BaseModel):
    label: str
    amount: Decimal
    color: str


class CoverSnapshot(BaseModel):
    position_date: Optional[date]
    # Round 13: "Overall" = Credit Sales (PDC) + Cash Balances combined, per
    # division -- this is what "Overall Cover Analysis" charts. The PDC-only
    # figures below power the second, PDC-only chart on the same page.
    receivables_by_division: list[CoverSnapshotSlice]
    dues_by_bank: list[CoverSnapshotSlice]
    total_receivables_sdg: Decimal
    total_dues_sdg: Decimal
    gap_sdg: Decimal
    # Active Dues / Overall Receivables * 100 (the user's own definition,
    # dues divided by receivables) -- None when there's nothing to divide by.
    cover_pct: Optional[Decimal] = None
    pdc_by_division: list[CoverSnapshotSlice] = []
    total_pdc_sdg: Decimal = Decimal("0")
    total_cash_sdg: Decimal = Decimal("0")
    gap_pdc_sdg: Decimal = Decimal("0")
    cover_pct_pdc: Optional[Decimal] = None
