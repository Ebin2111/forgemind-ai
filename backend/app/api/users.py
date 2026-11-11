"""User accounts (administrators only): list, add, change role / name / password, deactivate, delete."""
from fastapi import APIRouter, Depends, HTTPException, status as http
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from ..core.security import ADMIN, CurrentUser, hash_password, require_admin
from ..db import DbSession
from ..models.db_models import User
from ..schemas import DeleteOut, UserCreate, UserOut, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


def _user_or_404(db, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(http.HTTP_404_NOT_FOUND, "User not found.")
    return user


def _other_active_admins(db, user: User) -> int:
    return db.scalar(
        select(func.count()).select_from(User).where(User.role == ADMIN, User.is_active.is_(True), User.id != user.id)
    ) or 0


@router.get("", response_model=list[UserOut], summary="List all users")
def list_users(db: DbSession):
    return db.scalars(select(User).order_by(User.role, User.email)).all()


@router.post("", response_model=UserOut, status_code=http.HTTP_201_CREATED, summary="Add a user")
def create_user(body: UserCreate, db: DbSession):
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(http.HTTP_409_CONFLICT, f"{body.email} already has an account.")
    user = User(email=body.email, name=body.name, role=body.role, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(http.HTTP_409_CONFLICT, f"{body.email} already has an account.")
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=UserOut, summary="Edit a user")
def update_user(user_id: int, body: UserUpdate, db: DbSession, me: CurrentUser = Depends(require_admin)):
    user = _user_or_404(db, user_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    loses_admin = user.is_active and user.role == ADMIN and (
        changes.get("role", user.role) != ADMIN or changes.get("is_active", True) is False
    )
    if loses_admin:
        if user.email == me.email:
            raise HTTPException(http.HTTP_409_CONFLICT, "You cannot remove your own administrator access.")
        if not _other_active_admins(db, user):
            raise HTTPException(http.HTTP_409_CONFLICT, "At least one active administrator is required.")
    if "password" in changes:
        user.password_hash = hash_password(changes.pop("password"))
    for field, value in changes.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=DeleteOut, summary="Delete a user")
def delete_user(user_id: int, db: DbSession, me: CurrentUser = Depends(require_admin)):
    user = _user_or_404(db, user_id)
    if user.email == me.email:
        raise HTTPException(http.HTTP_409_CONFLICT, "You cannot delete your own account.")
    if user.role == ADMIN and user.is_active and not _other_active_admins(db, user):
        raise HTTPException(http.HTTP_409_CONFLICT, "At least one active administrator is required.")
    email = user.email
    db.delete(user)
    db.commit()
    return DeleteOut(deleted=email)