"""
Authentication module for OVH Checker API.
Provides JWT-based authentication with bcrypt password hashing.
"""
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import hashlib

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT Configuration
JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_urlsafe(32))
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Security scheme
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: int, email: str, is_admin: bool = False) -> str:
    """Create a JWT access token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "type": "access",
        "exp": expire,
        "iat": datetime.now(timezone.utc)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int) -> Tuple[str, str, datetime]:
    """
    Create a refresh token.
    Returns: (token, token_hash, expires_at)
    """
    token = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    return token, token_hash, expires_at


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


class AuthenticatedUser:
    """Represents an authenticated user from a JWT token."""
    def __init__(self, user_id: int, email: str, is_admin: bool = False):
        self.user_id = user_id
        self.email = email
        self.is_admin = is_admin


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[AuthenticatedUser]:
    """
    Get the current user from JWT token if provided.
    Returns None if no token or invalid token.
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload or payload.get("type") != "access":
        return None
    
    try:
        user_id = int(payload["sub"])
        email = payload["email"]
        is_admin = payload.get("is_admin", False)
        return AuthenticatedUser(user_id, email, is_admin)
    except (KeyError, ValueError):
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> AuthenticatedUser:
    """
    Get the current user from JWT token.
    Raises 401 if not authenticated.
    """
    user = await get_current_user_optional(credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_admin(
    user: AuthenticatedUser = Depends(get_current_user)
) -> AuthenticatedUser:
    """
    Require the current user to be an admin.
    Raises 403 if not admin.
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


def generate_api_key() -> Tuple[str, str]:
    """
    Generate an API key for programmatic access.
    Returns: (api_key, key_hash)
    """
    api_key = f"ovh_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    return api_key, key_hash


async def get_user_from_api_key(
    request: Request,
    db
) -> Optional[AuthenticatedUser]:
    """
    Get user from API key in X-API-Key header.
    Returns None if no API key or invalid.
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return None
    
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    user = await db.get_user_by_api_key(key_hash)
    
    if user:
        # Update last used timestamp
        await db.update_api_key_last_used(key_hash)
        return AuthenticatedUser(user["id"], user["email"], user["is_admin"])
    
    return None

