from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user, hash_password, require_manager
from ..database import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])


# ---------------------------------------------------------------- BUs ----
@router.get("/business-units", response_model=list[schemas.BusinessUnitOut])
def list_business_units(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.BusinessUnit).order_by(models.BusinessUnit.name).all()


@router.post("/business-units", response_model=schemas.BusinessUnitOut)
def create_business_unit(
    payload: schemas.BusinessUnitCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    if db.query(models.BusinessUnit).filter(models.BusinessUnit.name == payload.name).first():
        raise HTTPException(400, "A business unit with this name already exists.")
    bu = models.BusinessUnit(name=payload.name)
    db.add(bu)
    db.commit()
    db.refresh(bu)
    return bu


@router.put("/business-units/{bu_id}", response_model=schemas.BusinessUnitOut)
def update_business_unit(
    bu_id: int,
    payload: schemas.BusinessUnitUpdate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    bu = db.query(models.BusinessUnit).get(bu_id)
    if not bu:
        raise HTTPException(404, "Business unit not found.")
    dupe = (
        db.query(models.BusinessUnit)
        .filter(models.BusinessUnit.name == payload.name, models.BusinessUnit.id != bu_id)
        .first()
    )
    if dupe:
        raise HTTPException(400, "A business unit with this name already exists.")
    bu.name = payload.name
    db.commit()
    db.refresh(bu)
    return bu


@router.delete("/business-units/{bu_id}")
def delete_business_unit(
    bu_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_manager)
):
    bu = db.query(models.BusinessUnit).get(bu_id)
    if not bu:
        raise HTTPException(404, "Business unit not found.")
    division_count = (
        db.query(models.Division).filter(models.Division.business_unit_id == bu_id).count()
    )
    account_count = (
        db.query(models.MasterAccount).filter(models.MasterAccount.business_unit_id == bu_id).count()
    )
    if division_count or account_count:
        parts = []
        if division_count:
            parts.append(f"{division_count} division(s)")
        if account_count:
            parts.append(f"{account_count} account(s)")
        raise HTTPException(
            400,
            f"Can't delete '{bu.name}' -- still referenced by {' and '.join(parts)}. Reassign"
            " or remove those first.",
        )
    db.delete(bu)
    db.commit()
    return {"deleted": True}


# ------------------------------------------------------------ Divisions --
@router.get("/divisions", response_model=list[schemas.DivisionOut])
def list_divisions(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.Division).order_by(models.Division.name).all()


@router.post("/divisions", response_model=schemas.DivisionOut)
def create_division(
    payload: schemas.DivisionCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    bu = db.query(models.BusinessUnit).get(payload.business_unit_id)
    if not bu:
        raise HTTPException(400, "Unknown business unit.")
    division = models.Division(name=payload.name, business_unit_id=payload.business_unit_id)
    db.add(division)
    db.commit()
    db.refresh(division)
    return division


@router.put("/divisions/{division_id}", response_model=schemas.DivisionOut)
def update_division(
    division_id: int,
    payload: schemas.DivisionUpdate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    division = db.query(models.Division).get(division_id)
    if not division:
        raise HTTPException(404, "Division not found.")
    bu = db.query(models.BusinessUnit).get(payload.business_unit_id)
    if not bu:
        raise HTTPException(400, "Unknown business unit.")
    dupe = (
        db.query(models.Division)
        .filter(
            models.Division.name == payload.name,
            models.Division.business_unit_id == payload.business_unit_id,
            models.Division.id != division_id,
        )
        .first()
    )
    if dupe:
        raise HTTPException(400, "This business unit already has a division with this name.")
    division.name = payload.name
    division.business_unit_id = payload.business_unit_id
    db.commit()
    db.refresh(division)
    return division


@router.delete("/divisions/{division_id}")
def delete_division(
    division_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_manager)
):
    division = db.query(models.Division).get(division_id)
    if not division:
        raise HTTPException(404, "Division not found.")
    account_count = (
        db.query(models.MasterAccount).filter(models.MasterAccount.division_id == division_id).count()
    )
    if account_count:
        raise HTTPException(
            400,
            f"Can't delete '{division.name}' -- still referenced by {account_count} account(s)."
            " Reassign or remove those first.",
        )
    db.delete(division)
    db.commit()
    return {"deleted": True}


# ----------------------------------------------------------------Banks --
@router.get("/banks", response_model=list[schemas.BankOut])
def list_banks(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.Bank).order_by(models.Bank.short_name).all()


@router.post("/banks", response_model=schemas.BankOut)
def create_bank(
    payload: schemas.BankCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    if db.query(models.Bank).filter(models.Bank.short_name == payload.short_name).first():
        raise HTTPException(400, "A bank with this short name already exists.")
    bank = models.Bank(short_name=payload.short_name, full_name=payload.full_name)
    db.add(bank)
    db.commit()
    db.refresh(bank)
    return bank


@router.put("/banks/{bank_id}", response_model=schemas.BankOut)
def update_bank(
    bank_id: int,
    payload: schemas.BankUpdate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    bank = db.query(models.Bank).get(bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found.")
    dupe = (
        db.query(models.Bank)
        .filter(models.Bank.short_name == payload.short_name, models.Bank.id != bank_id)
        .first()
    )
    if dupe:
        raise HTTPException(400, "A bank with this short name already exists.")
    bank.short_name = payload.short_name
    bank.full_name = payload.full_name
    db.commit()
    db.refresh(bank)
    return bank


@router.delete("/banks/{bank_id}")
def delete_bank(
    bank_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_manager)
):
    bank = db.query(models.Bank).get(bank_id)
    if not bank:
        raise HTTPException(404, "Bank not found.")
    account_count = (
        db.query(models.MasterAccount).filter(models.MasterAccount.bank_id == bank_id).count()
    )
    if account_count:
        raise HTTPException(
            400,
            f"Can't delete '{bank.short_name}' -- still referenced by {account_count} account(s)."
            " Reassign or remove those first.",
        )
    db.delete(bank)
    db.commit()
    return {"deleted": True}


# ----------------------------------------------------------- Currencies --
@router.get("/currencies", response_model=list[schemas.CurrencyOut])
def list_currencies(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.Currency).order_by(models.Currency.code).all()


@router.post("/currencies", response_model=schemas.CurrencyOut)
def create_currency(
    payload: schemas.CurrencyCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    code = payload.code.upper()
    if db.query(models.Currency).filter(models.Currency.code == code).first():
        raise HTTPException(400, "This currency code already exists.")
    db.add(models.Currency(code=code))
    db.commit()
    return {"code": code}


@router.delete("/currencies/{code}")
def delete_currency(
    code: str, db: Session = Depends(get_db), _u: models.User = Depends(require_manager)
):
    code = code.upper()
    currency = db.query(models.Currency).get(code)
    if not currency:
        raise HTTPException(404, "Currency not found.")
    account_count = (
        db.query(models.MasterAccount).filter(models.MasterAccount.currency == code).count()
    )
    pair_count = (
        db.query(models.CurrencyPair)
        .filter(
            (models.CurrencyPair.base_currency == code) | (models.CurrencyPair.quote_currency == code)
        )
        .count()
    )
    if account_count or pair_count:
        parts = []
        if account_count:
            parts.append(f"{account_count} account(s)")
        if pair_count:
            parts.append(f"{pair_count} currency pair(s)")
        raise HTTPException(
            400,
            f"Can't delete '{code}' -- still referenced by {' and '.join(parts)}. Reassign"
            " or remove those first.",
        )
    db.delete(currency)
    db.commit()
    return {"deleted": True}


# ----------------------------------------------------------- Currency pairs
@router.get("/currency-pairs", response_model=list[schemas.CurrencyPairOut])
def list_currency_pairs(db: Session = Depends(get_db), _u: models.User = Depends(get_current_user)):
    return db.query(models.CurrencyPair).all()


@router.post("/currency-pairs", response_model=schemas.CurrencyPairOut)
def create_currency_pair(
    payload: schemas.CurrencyPairCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    existing = (
        db.query(models.CurrencyPair)
        .filter(
            models.CurrencyPair.base_currency == payload.base_currency,
            models.CurrencyPair.quote_currency == payload.quote_currency,
        )
        .first()
    )
    if existing:
        raise HTTPException(400, "This currency pair is already tracked.")
    supports_extended = "SDG" in (payload.base_currency, payload.quote_currency)
    pair = models.CurrencyPair(
        base_currency=payload.base_currency,
        quote_currency=payload.quote_currency,
        supports_extended_rates=supports_extended,
        is_default=False,
    )
    db.add(pair)
    db.commit()
    db.refresh(pair)
    return pair


@router.delete("/currency-pairs/{pair_id}")
def delete_currency_pair(
    pair_id: int, db: Session = Depends(get_db), _u: models.User = Depends(require_manager)
):
    pair = db.query(models.CurrencyPair).get(pair_id)
    if not pair:
        raise HTTPException(404, "Currency pair not found.")
    rate_count = db.query(models.FxRate).filter(models.FxRate.currency_pair_id == pair_id).count()
    if rate_count:
        raise HTTPException(
            400,
            f"Can't delete {pair.label} -- still referenced by {rate_count} FX rate entr(y/ies)."
            " Delete those first.",
        )
    db.delete(pair)
    db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------- Users --
@router.get("/users", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), _u: models.User = Depends(require_manager)):
    return db.query(models.User).order_by(models.User.username).all()


@router.post("/users", response_model=schemas.UserOut)
def create_user(
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    if payload.role not in ("Manager", "ReadWrite", "ReadOnly"):
        raise HTTPException(400, "Role must be Manager, ReadWrite, or ReadOnly.")
    if db.query(models.User).filter(models.User.username == payload.username).first():
        raise HTTPException(400, "This username is already taken.")
    user = models.User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        display_name=payload.display_name,
        email=payload.email,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/reset-password", response_model=schemas.UserOut)
def reset_password(
    user_id: int,
    payload: schemas.UserCreate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    """Manager-initiated password reset -- also how a migrated legacy user
    (old SHA256 password, can't be verified anymore) gets a usable password
    again."""
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    user.password_hash = hash_password(payload.password)
    db.commit()
    db.refresh(user)
    return user


@router.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(
    user_id: int,
    payload: schemas.UserUpdate,
    db: Session = Depends(get_db),
    _u: models.User = Depends(require_manager),
):
    if payload.role not in ("Manager", "ReadWrite", "ReadOnly"):
        raise HTTPException(400, "Role must be Manager, ReadWrite, or ReadOnly.")
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    dupe = (
        db.query(models.User)
        .filter(models.User.username == payload.username, models.User.id != user_id)
        .first()
    )
    if dupe:
        raise HTTPException(400, "This username is already taken.")
    if user.role == "Manager" and payload.role != "Manager":
        remaining_managers = (
            db.query(models.User)
            .filter(models.User.role == "Manager", models.User.id != user_id)
            .count()
        )
        if remaining_managers == 0:
            raise HTTPException(
                400, "Can't change this user's role -- they're the only Manager left."
            )
    user.username = payload.username
    user.role = payload.role
    user.display_name = payload.display_name
    user.email = payload.email
    db.commit()
    db.refresh(user)
    return user


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current: models.User = Depends(require_manager),
):
    if user_id == current.id:
        raise HTTPException(400, "You can't delete your own account while logged in as it.")
    user = db.query(models.User).get(user_id)
    if not user:
        raise HTTPException(404, "User not found.")
    if user.role == "Manager":
        remaining_managers = (
            db.query(models.User)
            .filter(models.User.role == "Manager", models.User.id != user_id)
            .count()
        )
        if remaining_managers == 0:
            raise HTTPException(400, "Can't delete the only remaining Manager.")
    db.delete(user)
    db.commit()
    return {"deleted": True}
