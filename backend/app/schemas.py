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


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "ReadWrite"


class UserUpdate(BaseModel):
    username: str
    role: str


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


class HomeSummary(BaseModel):
    as_of: Optional[date]
    total_receivables_sdg: Decimal
    total_dues_sdg: Decimal
    gap_sdg: Decimal
    gap_pct: Optional[Decimal]
    usd_sdg_rate: Optional[Decimal]
    usd_sdg_rate_date: Optional[date]
    gap_usd_equivalent: Optional[Decimal]
    status: str  # "covered" | "shortfall" | "no_data"
    unconverted_account_count: int
    notes: Optional[str] = None


class ImportRowError(BaseModel):
    row_number: int
    reason: str


class ImportResult(BaseModel):
    imported: int
    updated: int
    skipped: list[ImportRowError]


class CoverBreakdownRow(BaseModel):
    group_label: str
    total_receivables_sdg: Decimal
    total_dues_sdg: Decimal
    gap_sdg: Decimal
    status: str
    # Each group's receivables as a % of company-wide total receivables --
    # lets you see how much of the overall exposure a group represents even
    # when Dues can't be reliably attributed to the same group (e.g. Bank
    # Dues data that only identifies the Bank, not the Business
    # Unit/Division that will ultimately cover it).
    pct_of_total_receivables: Optional[Decimal] = None
