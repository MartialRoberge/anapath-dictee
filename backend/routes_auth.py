"""Routes d'authentification : inscription, login, refresh, profil."""

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from database import get_db_session
from db_models import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Modeles
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    """Requete d'inscription."""
    email: str
    password: str
    name: str


class LoginRequest(BaseModel):
    """Requete de connexion."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Reponse avec tokens JWT."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Requete de rafraichissement du token."""
    refresh_token: str


class UserResponse(BaseModel):
    """Profil utilisateur."""
    id: str
    email: str
    name: str
    role: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenResponse)
async def register(
    req: RegisterRequest,
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> TokenResponse:
    """Inscription d'un nouvel utilisateur."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail="Email deja utilise")

    user = User(
        email=req.email,
        password_hash=hash_password(req.password),
        name=req.name,
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id: str = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    req: LoginRequest,
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> TokenResponse:
    """Connexion d'un utilisateur existant."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    result = await db.execute(select(User).where(User.email == req.email))
    user: User | None = result.scalar_one_or_none()

    if user is None or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Compte desactive")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    user_id: str = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    req: RefreshRequest,
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> TokenResponse:
    """Rafraichissement du token d'acces."""
    if db is None:
        raise HTTPException(status_code=503, detail="Base de donnees non disponible")

    payload = decode_token(req.refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Token de rafraichissement invalide")

    user_id: str = payload.get("sub", "")
    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Utilisateur non trouve")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse)
async def me(
    user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    """Profil de l'utilisateur connecte."""
    return UserResponse(
        id=str(user.id),
        email=user.email,
        name=user.name,
        role=user.role,
    )
