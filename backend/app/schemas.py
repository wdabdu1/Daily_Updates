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


class BusinessUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BusinessUnitCreate(BaseModel):
    name: str


class DivisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    business_unit_id: int


class DivisionCreate(BaseModel):
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
    business_unit_id: int
    division_id: int
    bank_id: int
    account_name: str
    account_number: str
    currency: str
    business_unit_name: Optional[str] = None
    division_name: Optional[str] = None
    bank_short_name: Optional[str] = None


class MasterAccountCreate(BaseModel):
    business_unit_id: int
    division_id: int
    bank_id: int
    account_name: str
    account_number: str
    currency: str


class FxRateOut(BaseModel):
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
