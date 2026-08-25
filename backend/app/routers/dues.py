from decimal import InvalidOperation

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from .. import models, schemas
from ..auth import get_current_user, require_write
from ..database import get_db
from ..export_utils import parse_decimal, read_uploaded_xlsx, xlsx_response, xlsx_template_response

router = APIRouter(prefix="/api/dues", tags=["dues"])

DUES_TEMPLATE_COLUMNS = [
    "Business Unit",
    "Division",
    "Bank Short Name",
    "Bank Full Name",
    "Account Name",
    "Account Number",
    "Currency",
    "Due Date",
    "Facility Type",
    "Amount",
    "Status",
]


@router.get("", response_model=list[schemas.BankDueOut])
def list_dues(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    dues = (
        db.query(models.BankDue)
        .options(
            joinedload(models.BankDue.account).joinedload(models.MasterAccount.business_unit),
            joinedload(models.BankDue.account).joinedload(models.MasterAccount.division),
            joinedload(models.BankDue.account).joinedload(models.MasterAccount.bank),
        )
        .order_by(models.BankDue.due_date)
        .all()
    )
    out = []
    for d in dues:
        acct = d.account
        out.append(
            schemas.BankDueOut(
                id=d.id,
                account_id=d.account_id,
                due_date=d.due_date,
                facility_type=d.facility_type,
                amount=d.amount,
                status=d.status,
                business_unit_name=acct.business_unit.name if acct and acct.business_unit else None,
                division_name=acct.division.name if acct and acct.division else None,
                bank_short_name=acct.bank.short_name if acct and acct.bank else None,
                account_number=acct.account_number if acct else None,
            )
        )
    return out


@router.get("/export")
def export_dues(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    dues = (
        db.query(models.BankDue)
        .options(joinedload(models.BankDue.account))
        .order_by(models.BankDue.due_date)
        .all()
    )
    rows = [
        {
            "Account": f"{d.account.bank.short_name} - {d.account.account_number}" if d.account else "",
            "Due Date": d.due_date,
            "Facility Type": d.facility_type,
            "Amount": float(d.amount) if d.amount is not None else None,
            "Status": d.status,
        }
        for d in dues
    ]
    return xlsx_response(rows, "bank_dues.xlsx")


@router.post("", response_model=schemas.BankDueOut)
def create_due(
    payload: schemas.BankDueCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    due = models.BankDue(**payload.model_dump(), status="Active")
    db.add(due)
    db.commit()
    db.refresh(due)
    return due


@router.post("/{due_id}/settle", response_model=schemas.BankDueOut)
def settle_due(
    due_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_write)
):
    due = db.query(models.BankDue).get(due_id)
    if due:
        due.status = "Settled"
        db.commit()
        db.refresh(due)
    return due


@router.get("/import/template")
def dues_import_template(_u: models.User = Depends(get_current_user)):
    example_rows = [
        [
            "Corporate Treasury", "Operations", "CIB", "Commercial International Bank",
            "Treasury Main AED", "1001-AED", "SDG", "2026-09-10", "Overdraft", 300000, "Active",
        ],
        [
            "Logistics", "Freight", "ONB", "Omdurman National Bank",
            "Freight Ops SDG", "2002-SDG", "SDG", "2026-09-25", "Trade Finance", 250000, "Active",
        ],
        [
            "", "", "CIB", "Commercial International Bank",
            "Unattributed AED", "1003-AED", "SDG", "2026-09-30", "Overdraft", 150000, "Active",
        ],
    ]
    notes = [
        "Bank Short Name + Account Number together identify the account this due belongs to. If"
        " that combination doesn't exist yet under Settings, it's created automatically from this"
        " row (Bank Full Name is only used the first time a new Bank Short Name appears; Currency"
        " must already be a known code).",
        "Business Unit and Division are OPTIONAL -- leave them blank if you don't have reliable"
        " BU/Division attribution for this due yet (see the third example row). It shows up as"
        " 'Unassigned' in the Home/Analysis breakdowns until you know it, and you can fill it in"
        " later by re-uploading the same Bank + Account Number with the BU/Division now specified.",
        "Account Number + Bank Short Name together should be unique per account -- reusing the"
        " same pair on multiple rows refers to the same account each time.",
        "Re-uploading a row for the same account (Bank + Account Number) + Due Date + Facility"
        " Type UPDATES that due's Amount/Status rather than creating a duplicate -- this is how"
        " you correct test data or replace it with final figures.",
        "Due Date must be YYYY-MM-DD (or any format Excel stores as a real date).",
        "Status should be 'Active' or 'Settled'. Amount is a number, e.g. 300000 or 300,000.00 --"
        " thousands-separator commas are fine, just don't include a currency symbol.",
    ]
    return xlsx_template_response(
        DUES_TEMPLATE_COLUMNS, example_rows, notes, "bank_dues_template.xlsx"
    )


def _get_or_create_bu(db: Session, name: str) -> models.BusinessUnit | None:
    """Business Unit is optional on an account -- some Bank Dues data only
    reliably identifies the Bank/Account, not which BU/Division will
    ultimately cover it. A blank cell leaves the account's business_unit_id
    NULL (shown as "Unassigned" in breakdowns) rather than inventing a
    placeholder BU."""
    name = (name or "").strip()
    if not name or name.lower() == "nan":
        return None
    bu = db.query(models.BusinessUnit).filter(models.BusinessUnit.name == name).first()
    if not bu:
        bu = models.BusinessUnit(name=name)
        db.add(bu)
        db.flush()
    return bu


def _get_or_create_division(db: Session, name: str, bu_id: int | None) -> models.Division | None:
    """Optional for the same reason as _get_or_create_bu -- also requires a
    known BU, since a Division only makes sense scoped to one."""
    name = (name or "").strip()
    if not name or name.lower() == "nan" or bu_id is None:
        return None
    division = (
        db.query(models.Division)
        .filter(models.Division.name == name, models.Division.business_unit_id == bu_id)
        .first()
    )
    if not division:
        division = models.Division(name=name, business_unit_id=bu_id)
        db.add(division)
        db.flush()
    return division


def _get_or_create_bank(db: Session, short_name: str, full_name: str) -> models.Bank:
    bank = db.query(models.Bank).filter(models.Bank.short_name == short_name).first()
    if not bank:
        bank = models.Bank(short_name=short_name, full_name=full_name or short_name)
        db.add(bank)
        db.flush()
    return bank


def _get_or_create_account(
    db: Session,
    bu_id: int | None,
    division_id: int | None,
    bank_id: int,
    account_name: str,
    account_number: str,
    currency: str,
) -> models.MasterAccount:
    account = (
        db.query(models.MasterAccount)
        .filter(
            models.MasterAccount.bank_id == bank_id,
            models.MasterAccount.account_number == account_number,
        )
        .first()
    )
    if not account:
        account = models.MasterAccount(
            business_unit_id=bu_id,
            division_id=division_id,
            bank_id=bank_id,
            account_name=account_name,
            account_number=account_number,
            currency=currency,
        )
        db.add(account)
        db.flush()
    return account


@router.post("/import", response_model=schemas.ImportResult)
def dues_import(
    file: UploadFile,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_write),
):
    try:
        df = read_uploaded_xlsx(file.file.read())
    except Exception as e:
        raise HTTPException(400, f"Couldn't read this file as an Excel workbook: {e}")

    missing = [c for c in DUES_TEMPLATE_COLUMNS if c not in df.columns]
    if missing:
        raise HTTPException(
            400,
            f"Missing column(s): {', '.join(missing)}. Download the template to see the"
            " expected columns.",
        )

    imported = 0
    updated = 0
    errors: list[schemas.ImportRowError] = []

    for idx, row in df.iterrows():
        row_number = idx + 2
        try:
            bu_name = str(row["Business Unit"]).strip()
            division_name = str(row["Division"]).strip()
            bank_short = str(row["Bank Short Name"]).strip()
            bank_full = str(row["Bank Full Name"]).strip() if pd.notna(row["Bank Full Name"]) else ""
            account_name = str(row["Account Name"]).strip()
            account_number = str(row["Account Number"]).strip()
            currency = str(row["Currency"]).strip().upper()
            raw_due_date = row["Due Date"]
            try:
                due_date = (
                    raw_due_date.date()
                    if hasattr(raw_due_date, "date")
                    else pd.to_datetime(raw_due_date).date()
                )
            except Exception:
                raise ValueError(
                    f"'{raw_due_date}' in the Due Date column isn't a valid calendar date -- this"
                    " usually happens when a date column is stored as text and Excel's fill-handle"
                    " just increments the trailing number (e.g. ...-08-31 becomes ...-08-32 instead"
                    " of rolling over to September). Format the column as a real Date and re-enter it."
                )
            facility_type = str(row["Facility Type"]).strip()
            amount = parse_decimal(row["Amount"])
            status = str(row["Status"]).strip().title() if pd.notna(row["Status"]) else "Active"
            # Business Unit / Division are optional -- some Bank Dues data
            # only reliably identifies the Bank/Account (see
            # _get_or_create_bu/_get_or_create_division). Bank + Account
            # Number are still required to identify which account this due
            # belongs to.
            if not bank_short or not account_number:
                raise ValueError("Bank Short Name and Account Number are required.")
        except (ValueError, InvalidOperation, TypeError) as e:
            errors.append(schemas.ImportRowError(row_number=row_number, reason=f"Couldn't parse row: {e}"))
            continue

        if not db.query(models.Currency).get(currency):
            errors.append(
                schemas.ImportRowError(
                    row_number=row_number,
                    reason=f"Unknown currency code '{currency}' -- add it under Settings first.",
                )
            )
            continue

        # Each row's writes run inside their own SAVEPOINT (nested transaction).
        # Without this, a DB-level failure on one row (e.g. a constraint we
        # didn't anticipate) leaves the whole session unusable for every row
        # after it, and the entire import fails with an opaque 500 instead of
        # a clear per-row skip reason.
        try:
            with db.begin_nested():
                bu = _get_or_create_bu(db, bu_name)
                division = _get_or_create_division(db, division_name, bu.id if bu else None)
                bank = _get_or_create_bank(db, bank_short, bank_full)
                account = _get_or_create_account(
                    db,
                    bu.id if bu else None,
                    division.id if division else None,
                    bank.id,
                    account_name or account_number,
                    account_number,
                    currency,
                )

                existing = (
                    db.query(models.BankDue)
                    .filter(
                        models.BankDue.account_id == account.id,
                        models.BankDue.due_date == due_date,
                        models.BankDue.facility_type == facility_type,
                    )
                    .first()
                )
                if existing:
                    existing.amount = amount
                    existing.status = status
                    row_was_update = True
                else:
                    db.add(
                        models.BankDue(
                            account_id=account.id,
                            due_date=due_date,
                            facility_type=facility_type,
                            amount=amount,
                            status=status,
                        )
                    )
                    row_was_update = False
        except Exception as e:
            errors.append(
                schemas.ImportRowError(row_number=row_number, reason=f"Couldn't save row: {e}")
            )
            continue

        if row_was_update:
            updated += 1
        else:
            imported += 1

    db.commit()
    return schemas.ImportResult(imported=imported, updated=updated, skipped=errors)
