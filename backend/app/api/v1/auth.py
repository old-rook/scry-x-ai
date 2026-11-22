from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import get_authenticated_user, require_admin
from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import get_session
from app.db.models import User
from app.repositories.users import UserRepository
from app.schemas.auth import AuthResponse, LoginRequest, LogoutResponse, RegisterRequest


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: Request,
    body: RegisterRequest,
    session: Session = Depends(get_session),
) -> AuthResponse:
    if request.app.state.settings.jwt_signing_key is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    if UserRepository.get_by_email(session, body.email) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        user = UserRepository.create_authenticated(session, body.email, hash_password(body.password))
        session.commit()
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid password")
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    try:
        token = create_access_token(request.app.state.settings, user.id, user.role)
    except RuntimeError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    return AuthResponse(access_token=token, user_id=str(user.id), email=user.email or "", role=user.role)


@router.post("/login", response_model=AuthResponse)
def login(
    request: Request,
    body: LoginRequest,
    session: Session = Depends(get_session),
) -> AuthResponse:
    if request.app.state.settings.jwt_signing_key is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    user = UserRepository.get_by_email(session, body.email)
    if user is None or user.password_hash is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    try:
        token = create_access_token(request.app.state.settings, user.id, user.role)
    except RuntimeError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Authentication is not configured")
    return AuthResponse(access_token=token, user_id=str(user.id), email=user.email or "", role=user.role)


@router.post("/logout", response_model=LogoutResponse)
def logout(_: Annotated[User, Depends(get_authenticated_user)]) -> LogoutResponse:
    return LogoutResponse()


admin_router = APIRouter(prefix="/admin", tags=["admin"])


@admin_router.get("/status")
def admin_status(_: Annotated[User, Depends(require_admin)]) -> dict:
    return {"status": "ok"}
