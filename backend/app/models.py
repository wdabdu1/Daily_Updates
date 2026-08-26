from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)  # bcrypt
    # Manager: full access + Settings
    # ReadWrite: full access to Home/Analysis/BankDues/FX, no Settings
    # ReadOnly: view everything except Settings, cannot submit forms
    role = Column(String(20), nullable=False, default="ReadWrite")
    created_at = Column(DateTime, default=datetime.utcnow)
    # Round 12: optional profile fields, editable by a Manager (Settings >
    # Users) or by the user themselves (the top-right profile menu, see
    # auth.py's /me PATCH). Both nullable -- neither was ever required
    # before, and migrated/legacy users have neither set.
    display_name = Column(String(150), nullable=True)
    email = Column(String(255), nullable=True)


class BusinessUnit(Base):
    __tablename__ = "business_units"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)

    divisions = relationship("Division", back_populates="business_unit")


class Division(Base):
    __tablename__ = "divisions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    business_unit_id = Column(Integer, ForeignKey("business_units.id"), nullable=False)

    business_unit = relationship("BusinessUnit", back_populates="divisions")

    __table_args__ = (UniqueConstraint("name", "business_unit_id", name="uq_division_per_bu"),)


class Bank(Base):
    __tablename__ = "banks"

    id = Column(Integer, primary_key=True)
    short_name = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(150), nullable=False)


class Currency(Base):
    __tablename__ = "currencies"

    code = Column(String(10), primary_key=True)


class CurrencyPair(Base):
    __tablename__ = "currency_pairs"

    id = Column(Integer, primary_key=True)
    base_currency = Column(String(10), ForeignKey("currencies.code"), nullable=False)
    quote_currency = Column(String(10), ForeignKey("currencies.code"), nullable=False)
    # True when quote_currency == "SDG" (or base == SDG) -- these pairs get
    # CBOS + Pricing rates in addition to Market. Stored explicitly so the
    # rule survives even if SDG-detection logic changes later.
    supports_extended_rates = Column(Boolean, default=False)
    is_default = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("base_currency", "quote_currency", name="uq_currency_pair"),
    )

    @property
    def label(self):
        return f"{self.base_currency}/{self.quote_currency}"


class MasterAccount(Base):
    __tablename__ = "master_accounts"

    id = Column(Integer, primary_key=True)
    # Nullable: some Bank Dues data only identifies the Bank/Account, with no
    # reliable Business Unit or Division attribution yet (mixed/unspecified
    # in the source data). Left as "Unassigned" until dedicated per-division
    # dues data is available -- see home.py's breakdown grouping.
    business_unit_id = Column(Integer, ForeignKey("business_units.id"), nullable=True)
    division_id = Column(Integer, ForeignKey("divisions.id"), nullable=True)
    bank_id = Column(Integer, ForeignKey("banks.id"), nullable=False)
    account_name = Column(String(150), nullable=False)
    account_number = Column(String(100), nullable=False)
    currency = Column(String(10), ForeignKey("currencies.code"), nullable=False)

    business_unit = relationship("BusinessUnit")
    division = relationship("Division")
    bank = relationship("Bank")


class FxRate(Base):
    __tablename__ = "fx_rates"

    id = Column(Integer, primary_key=True)
    rate_date = Column(Date, nullable=False)
    currency_pair_id = Column(Integer, ForeignKey("currency_pairs.id"), nullable=False)
    rate_type = Column(String(20), nullable=False)  # Market | CBOS | Pricing
    rate = Column(Numeric(15, 4), nullable=False)
    # True when this row was entered directly by a user; the carry-forward
    # fill is computed at query time, not persisted, so gaps stay visible.
    is_manual_entry = Column(Boolean, default=True)

    currency_pair = relationship("CurrencyPair")

    __table_args__ = (
        UniqueConstraint(
            "rate_date", "currency_pair_id", "rate_type", name="uq_rate_date_pair_type"
        ),
    )


class BankDue(Base):
    __tablename__ = "bank_dues"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("master_accounts.id", ondelete="CASCADE"))
    due_date = Column(Date)
    facility_type = Column(String(100))
    # 20 digits before the decimal point -- SDG amounts routinely run into
    # the hundreds of millions/billions given the currency's devaluation, so
    # this needs real headroom (see schema_upgrades.py: this column started
    # narrower on the live Postgres table and widening it here alone didn't
    # take effect there, since create_all() never ALTERs an existing column).
    amount = Column(Numeric(20, 2))
    status = Column(String(50), default="Active")

    account = relationship("MasterAccount")


class ReceivableDaily(Base):
    """Legacy, account/bank-linked daily receivables. As of Round 11, Home
    and Analysis no longer read this table -- receivables moved to a
    division-level, bank-agnostic figure (see DivisionReceivableDaily
    below), since the real-world cash a division holds spans multiple
    banks/cash-in-hand and was never meaningfully "one bank account's
    balance" in the first place. Kept, not dropped: this table's history
    predates the switch and the user chose not to migrate/aggregate it into
    the new table (a clean division mapping wasn't guaranteed for every past
    entry) -- it simply stops being written to or read from going forward."""

    __tablename__ = "receivables_daily"

    id = Column(Integer, primary_key=True)
    position_date = Column(Date, nullable=False, default=date.today)
    account_id = Column(Integer, ForeignKey("master_accounts.id", ondelete="CASCADE"))
    amount = Column(Numeric(20, 2), nullable=False, default=0)

    account = relationship("MasterAccount")

    __table_args__ = (
        UniqueConstraint("position_date", "account_id", name="uq_position_account"),
    )


class DivisionReceivableDaily(Base):
    """Round 11: a division's total accumulated cash position for a given
    day -- one already-in-SDG figure per division per day, deliberately NOT
    linked to any bank/account (a division's cash can span several banks
    plus cash-in-hand, and attributing it to one bank was never accurate).
    Replaces ReceivableDaily as the source Home/Analysis read for the
    receivables side of the cover calculation."""

    __tablename__ = "division_receivables_daily"

    id = Column(Integer, primary_key=True)
    position_date = Column(Date, nullable=False, default=date.today)
    division_id = Column(Integer, ForeignKey("divisions.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(20, 2), nullable=False, default=0)

    division = relationship("Division")

    __table_args__ = (
        UniqueConstraint("position_date", "division_id", name="uq_position_division"),
    )
