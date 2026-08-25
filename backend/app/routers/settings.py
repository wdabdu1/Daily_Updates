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
