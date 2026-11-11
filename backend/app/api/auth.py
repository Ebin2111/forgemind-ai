"""Sign-in endpoints: log in (sets the session cookie), log out, who am I, and change my own password."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select

from ..core.config import settings
from ..core.security import (
    COOKIE_NAME, CurrentUser, authenticate, create_session_token, hash_password, login_throttle, password_problem,
    require_user, verify_password,
)
from ..db import DbSession
from ..models.db_models import User
from ..schemas import ChangePassword, LoginRequest, SessionOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _session_out(user: CurrentUser) -> SessionOut:
    return SessionOut(email=user.email, name=user.name, role=user.role, auth_required=settings.auth_enabled)


@router.post("/login", response_model=SessionOut, summary="Sign in and receive the session cookie")
def login(body: LoginRequest, request: Request, response: Response, db: DbSession) -> SessionOut:
    if not settings.auth_enabled:
        return SessionOut(email="local", name="Local user", role="admin", auth_required=False)

    client = _client_key(request)
    wait = login_throttle.retry_after(client)
    if wait:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a minute and try again.",
                            headers={"Retry-After": str(wait)})

    user = authenticate(db, body.email, body.password)
    if user is None:
        login_throttle.record_failure(client)
        logger.warning("Failed sign-in from %s", client)  # the attempted email and password are never logged
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    login_throttle.reset(client)
    ttl = settings.remember_days * 86400 if body.remember else settings.session_hours * 3600
    response.set_cookie(
        COOKIE_NAME, create_session_token(user.email, ttl),
        max_age=ttl if body.remember else None,  # without "Remember me" the cookie ends with the browser session
        httponly=True, samesite="lax", secure=settings.is_production, path="/",
    )
    logger.info("Signed in %s (%s) from %s", user.email, user.role, client)
    return _session_out(CurrentUser(user.email, user.name, user.role))


@router.post("/logout", status_code=204, summary="Sign out")
def logout() -> Response:
    response = Response(status_code=204)
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, samesite="lax", secure=settings.is_production)
    return response


@router.get("/me", response_model=SessionOut, summary="Who is signed in (401 when nobody is)")
def me(user: CurrentUser = Depends(require_user)) -> SessionOut:
    return _session_out(user)


@router.post("/change-password", status_code=204, summary="Change your own password")
def change_password(body: ChangePassword, db: DbSession, current: CurrentUser = Depends(require_user)) -> Response:
    if not settings.auth_enabled:
        raise HTTPException(status_code=400, detail="Passwords are not used while sign-in is switched off.")
    user = db.scalar(select(User).where(User.email == current.email))
    if user is None or not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Your current password is not correct.")
    problem = password_problem(body.new_password)
    if problem:
        raise HTTPException(status_code=422, detail=problem)
    if body.new_password == body.current_password:
        raise HTTPException(status_code=422, detail="Choose a password that is different from the current one.")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return Response(status_code=204)