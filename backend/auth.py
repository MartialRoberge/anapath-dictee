"""Authentification JWT pour l'API Lexia.

Fournit :
- Hashage et verification des mots de passe (bcrypt)
- Creation et validation des tokens JWT (access + refresh)
- Dependency FastAPI pour extraire l'utilisateur courant
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import get_db_session
from db_models import User

_bearer_scheme = HTTPBearer(auto_error=False)


# ---------------------------------------------------------------------------
# Mots de passe
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Hash un mot de passe en bcrypt."""
    salt: bytes = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifie un mot de passe contre son hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ---------------------------------------------------------------------------
# Tokens JWT
# ---------------------------------------------------------------------------


def create_access_token(user_id: str) -> str:
    """Cree un access token JWT."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_minutes
    )
    payload: dict[str, str | datetime] = {
        "sub": user_id,
        "exp": expire,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """Cree un refresh token JWT."""
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.jwt_refresh_token_days
    )
    payload: dict[str, str | datetime] = {
        "sub": user_id,
        "exp": expire,
        "type": "refresh",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, str]:
    """Decode un token JWT et retourne le payload."""
    settings = get_settings()
    try:
        payload: dict[str, str] = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expire",
        ) from exc


# ---------------------------------------------------------------------------
# Dependency FastAPI : utilisateur courant
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    db: Annotated[AsyncSession | None, Depends(get_db_session)],
) -> User:
    """Extrait l'utilisateur courant depuis le token JWT."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token manquant",
        )
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Base de donnees non disponible",
        )

    payload = decode_token(credentials.credentials)
    user_id: str | None = payload.get("sub")
    token_type: str | None = payload.get("type")

    if not user_id or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
        )

    result = await db.execute(select(User).where(User.id == user_id))
    user: User | None = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur non trouve ou desactive",
        )

    return user


async def get_admin_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Verifie que l'utilisateur est admin."""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acces reserve aux administrateurs",
        )
    return user
