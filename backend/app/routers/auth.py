from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import create_access_token, get_current_user, hash_password, verify_password
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password."
        )
    token = create_access_token(user.username, user.role)
    return schemas.TokenResponse(access_token=token, role=user.role, username=user.username)


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=schemas.UserOut)
def update_me(
    payload: schemas.MeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Self-service profile edit -- any logged-in user, any role, can set
    their own display name/email. Deliberately does not touch username or
    role (those stay Manager-only, via Settings > Users)."""
    current_user.display_name = payload.display_name
    current_user.email = payload.email
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/change-password")
def change_password(
    payload: schemas.ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Self-service password change -- requires the current password
    (unlike Settings > Users' Manager-initiated reset, which doesn't)."""
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect.")
    if len(payload.new_password) < 4:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password is too short.")
    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"changed": True}
