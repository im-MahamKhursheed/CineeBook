"""
CineBook   – Authentication & Authorization
=============================================
JWT-based stateless auth.
  • POST /auth/register  → creates User
  • POST /auth/login     → returns Bearer token
  • Dependency `require_user`  → any authenticated user
  • Dependency `require_admin` → role == 'admin' only
"""

from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Annotated, Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from .database import get_db
from .models import User, UserRole

# ─── Config  ──────────────

SECRET_KEY    = os.getenv("SECRET_KEY", "cinebook-dev-secret-change-in-prod")
ALGORITHM     = "HS256"
TOKEN_EXPIRE  = int(os.getenv("TOKEN_EXPIRE_MINUTES", "60"))  # 1 hour default

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ─── Password helpers  ────

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


# ─── JWT helpers  ─────────

def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE)
    payload = {
        "sub"     : str(user.id),
        "username": user.username,
        "role"    : user.role.value,
        "exp"     : expire,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── FastAPI dependencies  

def require_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db   : Annotated[Any, Depends(get_db)],
) -> User:
    """Dependency: returns the current User; raises 401 if unauthenticated."""
    payload = _decode_token(token)
    user_id = int(payload["sub"])
    user_doc = db.users.find_one({"_id": user_id, "is_active": True})
    if not user_doc:
        raise HTTPException(status_code=401, detail="User not found or deactivated.")
    return User(**user_doc)


def require_admin(current_user: Annotated[User, Depends(require_user)]) -> User:
    """Dependency: raises 403 if the caller is not an admin."""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return current_user
