"""Authentication endpoints."""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Request

from auth import (
    AuthenticatedUser,
    get_current_user,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from db_instance import db
from models import (
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
)

# Import rate limiter from main app
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/auth", tags=["authentication"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit("5/minute")  # Rate limit: 5 registrations per minute per IP
async def register(request: Request, user_data: UserRegister):
    """Register a new user."""
    # Check if registration is enabled
    allow_registration = await db.get_config("allow_registration")
    if allow_registration != "true":
        raise HTTPException(status_code=403, detail="Public registration is disabled")
    
    # Check if email exists
    if await db.check_email_exists(user_data.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Check if username exists
    if await db.check_username_exists(user_data.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Create user
    password_hash = hash_password(user_data.password)
    user = await db.create_user(user_data.email, user_data.username, password_hash)
    
    if not user:
        raise HTTPException(status_code=400, detail="Failed to create user")
    
    # Generate tokens
    access_token = create_access_token(user["id"], user["email"], user["is_admin"])
    refresh_token, token_hash, expires_at = create_refresh_token(user["id"])
    
    # Save refresh token
    await db.save_refresh_token(user["id"], token_hash, expires_at)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # Rate limit: 10 login attempts per minute per IP
async def login(request: Request, credentials: UserLogin):
    """Login and get access token."""
    user = await db.get_user_by_email(credentials.email)
    
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    # Update last login
    await db.update_user_login(user["id"])
    
    # Generate tokens
    access_token = create_access_token(user["id"], user["email"], user["is_admin"])
    refresh_token, token_hash, expires_at = create_refresh_token(user["id"])
    
    # Save refresh token
    await db.save_refresh_token(user["id"], token_hash, expires_at)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    token_hash = hash_refresh_token(request.refresh_token)
    token_info = await db.get_refresh_token(token_hash)
    
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    if token_info["revoked_at"]:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    
    # Use timezone-aware comparison
    expires_at = token_info["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    
    if not token_info["is_active"]:
        raise HTTPException(status_code=403, detail="Account is disabled")
    
    # Revoke old refresh token
    await db.revoke_refresh_token(token_hash)
    
    # Generate new tokens
    access_token = create_access_token(
        token_info["user_id"], 
        token_info["email"], 
        token_info["is_admin"]
    )
    new_refresh_token, new_token_hash, expires_at = create_refresh_token(token_info["user_id"])
    
    # Save new refresh token
    await db.save_refresh_token(token_info["user_id"], new_token_hash, expires_at)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/logout")
async def logout(
    request: RefreshTokenRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Logout and revoke refresh token."""
    token_hash = hash_refresh_token(request.refresh_token)
    await db.revoke_refresh_token(token_hash)
    return {"status": "ok", "message": "Logged out successfully"}


@router.post("/logout-all")
async def logout_all(user: AuthenticatedUser = Depends(get_current_user)):
    """Logout from all devices by revoking all refresh tokens."""
    await db.revoke_all_user_tokens(user.user_id)
    return {"status": "ok", "message": "Logged out from all devices"}
