import logging
import secrets
import string
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Optional
import os

from config import settings
from database import Database
from auth import (
    AuthenticatedUser,
    get_current_user,
    get_current_user_optional,
    get_current_admin,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    generate_api_key,
    ACCESS_TOKEN_EXPIRE_MINUTES
)
from models import (
    # Auth models
    UserRegister,
    UserLogin,
    TokenResponse,
    RefreshTokenRequest,
    UserProfile,
    UserProfileUpdate,
    PasswordChange,
    # Webhook models
    UserWebhookCreate,
    UserWebhookUpdate,
    UserWebhook,
    # Subscription models
    PlanSubscriptionCreate,
    PlanSubscriptionUpdate,
    PlanSubscription,
    BulkSubscriptionUpdate,
    # API Key models
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyInfo,
    # Admin models
    AdminUserCreate,
    AdminUserUpdate,
    AdminUser,
    # Group models
    GroupCreate,
    GroupUpdate,
    Group,
    GroupMemberAdd,
    GroupMember,
    # Config models
    ConfigUpdate,
    DiscordWebhookConfig,
    RegistrationToggle,
    MonitoredPlanCreate,
    MonitoredPlanUpdate,
    InventoryStatus,
    StatusHistory,
    NotificationHistory,
    TestWebhookResponse,
    UserNotificationHistory
)
from discord_client import send_test_notification

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

db = Database(settings.database_url)


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


async def bootstrap_admin_user():
    """Create initial admin user if no users exist."""
    users = await db.get_all_users()
    if users:
        return  # Users already exist, skip bootstrap
    
    # Generate random password
    password = generate_secure_password(20)
    password_hash = hash_password(password)
    
    # Create admin user
    admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
    admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
    
    result = await db.admin_create_user(
        email=admin_email,
        username=admin_username,
        password_hash=password_hash,
        is_active=True,
        is_admin=True
    )
    
    if result:
        logger.info("="*60)
        logger.info("🔐 INITIAL ADMIN USER CREATED")
        logger.info("="*60)
        logger.info(f"   Email:    {admin_email}")
        logger.info(f"   Username: {admin_username}")
        logger.info(f"   Password: {password}")
        logger.info("="*60)
        logger.info("⚠️  SAVE THIS PASSWORD - IT WILL NOT BE SHOWN AGAIN!")
        logger.info("="*60)
    else:
        logger.error("Failed to create initial admin user")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    logger.info("Connected to database")
    
    # Bootstrap admin user if needed
    await bootstrap_admin_user()
    
    yield
    await db.disconnect()
    logger.info("Disconnected from database")


app = FastAPI(
    title="OVH Inventory Checker API",
    description="API for monitoring OVH VPS availability with multi-tenant support",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Authentication Endpoints ============

@app.post("/api/auth/register", response_model=TokenResponse)
async def register(user_data: UserRegister):
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


@app.post("/api/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
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


@app.post("/api/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    token_hash = hash_refresh_token(request.refresh_token)
    token_info = await db.get_refresh_token(token_hash)
    
    if not token_info:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    
    if token_info["revoked_at"]:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")
    
    if token_info["expires_at"].replace(tzinfo=None) < __import__('datetime').datetime.utcnow():
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


@app.post("/api/auth/logout")
async def logout(
    request: RefreshTokenRequest,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Logout and revoke refresh token."""
    token_hash = hash_refresh_token(request.refresh_token)
    await db.revoke_refresh_token(token_hash)
    return {"status": "ok", "message": "Logged out successfully"}


@app.post("/api/auth/logout-all")
async def logout_all(user: AuthenticatedUser = Depends(get_current_user)):
    """Logout from all devices by revoking all refresh tokens."""
    await db.revoke_all_user_tokens(user.user_id)
    return {"status": "ok", "message": "Logged out from all devices"}


# ============ User Profile Endpoints ============

@app.get("/api/me", response_model=UserProfile)
async def get_profile(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's profile."""
    profile = await db.get_user_by_id(user.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@app.put("/api/me")
async def update_profile(
    update: UserProfileUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Update current user's profile."""
    if update.username:
        # Check if username is taken by another user
        existing = await db.get_user_by_email(update.username)
        if existing and existing["id"] != user.user_id:
            raise HTTPException(status_code=400, detail="Username already taken")
    
    success = await db.update_user_profile(user.user_id, update.username)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update profile")
    
    return {"status": "ok", "message": "Profile updated"}


@app.post("/api/me/password")
async def change_password(
    data: PasswordChange,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Change current user's password."""
    # Verify current password
    user_data = await db.get_user_by_email(user.email)
    if not verify_password(data.current_password, user_data["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    # Update password
    new_hash = hash_password(data.new_password)
    await db.update_user_password(user.user_id, new_hash)
    
    # Revoke all refresh tokens to force re-login
    await db.revoke_all_user_tokens(user.user_id)
    
    return {"status": "ok", "message": "Password changed. Please login again."}


# ============ User Webhooks Endpoints ============

@app.get("/api/me/webhooks", response_model=List[UserWebhook])
async def get_my_webhooks(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's Discord webhooks."""
    webhooks = await db.get_user_webhooks(user.user_id)
    # Mask webhook URLs for security
    for wh in webhooks:
        url = wh["webhook_url"]
        if len(url) > 40:
            wh["webhook_url_masked"] = url[:30] + "..." + url[-10:]
        else:
            wh["webhook_url_masked"] = "***configured***"
    return webhooks


@app.post("/api/me/webhooks", response_model=UserWebhook)
async def create_my_webhook(
    webhook: UserWebhookCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Create a new Discord webhook for current user with customization options."""
    webhook_id = await db.create_user_webhook(
        user_id=user.user_id, 
        webhook_url=webhook.webhook_url, 
        webhook_name=webhook.webhook_name,
        bot_username=webhook.bot_username,
        avatar_url=webhook.avatar_url,
        include_price=webhook.include_price,
        include_specs=webhook.include_specs,
        mention_role_id=webhook.mention_role_id,
        embed_color=webhook.embed_color
    )
    return await db.get_user_webhook(user.user_id, webhook_id)


@app.put("/api/me/webhooks/{webhook_id}")
async def update_my_webhook(
    webhook_id: int,
    update: UserWebhookUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Update a Discord webhook with customization options."""
    success = await db.update_user_webhook(
        user_id=user.user_id, 
        webhook_id=webhook_id, 
        webhook_name=update.webhook_name,
        bot_username=update.bot_username,
        avatar_url=update.avatar_url,
        include_price=update.include_price,
        include_specs=update.include_specs,
        mention_role_id=update.mention_role_id,
        embed_color=update.embed_color,
        is_active=update.is_active
    )
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "ok"}


@app.delete("/api/me/webhooks/{webhook_id}")
async def delete_my_webhook(
    webhook_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Delete a Discord webhook."""
    success = await db.delete_user_webhook(user.user_id, webhook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "ok"}


@app.post("/api/me/webhooks/{webhook_id}/test", response_model=TestWebhookResponse)
async def test_my_webhook(
    webhook_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Test a user's Discord webhook."""
    webhook = await db.get_user_webhook(user.user_id, webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    success, message = await send_test_notification(webhook["webhook_url"])
    
    # Save to user notification history
    await db.save_user_notification(
        plan_code="TEST",
        datacenter="TEST",
        message="Test notification",
        success=success,
        error_message=None if success else message,
        user_id=user.user_id,
        webhook_id=webhook_id
    )
    
    return TestWebhookResponse(success=success, message=message)


# ============ User Plan Subscriptions Endpoints ============

@app.get("/api/me/subscriptions", response_model=List[PlanSubscription])
async def get_my_subscriptions(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's plan subscriptions."""
    return await db.get_user_subscriptions(user.user_id)


@app.post("/api/me/subscriptions")
async def add_my_subscription(
    subscription: PlanSubscriptionCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Subscribe to notifications for a plan in a specific subsidiary."""
    subsidiary = getattr(subscription, 'subsidiary', 'US')
    sub_id = await db.add_user_subscription(
        user.user_id,
        subscription.plan_code,
        subsidiary,
        subscription.notify_on_available
    )
    if sub_id is None:
        raise HTTPException(status_code=400, detail="Invalid plan code or subsidiary")
    return {"status": "ok", "id": sub_id}


@app.put("/api/me/subscriptions/{plan_code}")
async def update_my_subscription(
    plan_code: str,
    update: PlanSubscriptionUpdate,
    subsidiary: Optional[str] = Query(None, description="Subsidiary (required for update)"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Update subscription settings for a plan."""
    if not subsidiary:
        raise HTTPException(status_code=400, detail="Subsidiary is required")
    success = await db.update_user_subscription(
        user.user_id,
        plan_code,
        subsidiary.upper(),
        update.notify_on_available
    )
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"status": "ok"}


@app.delete("/api/me/subscriptions/{plan_code}")
async def remove_my_subscription(
    plan_code: str,
    subsidiary: Optional[str] = Query(None, description="Subsidiary (or all if omitted)"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Unsubscribe from notifications for a plan."""
    success = await db.remove_user_subscription(
        user.user_id, 
        plan_code, 
        subsidiary.upper() if subsidiary else None
    )
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return {"status": "ok"}


@app.post("/api/me/subscriptions/bulk")
async def bulk_update_subscriptions(
    data: BulkSubscriptionUpdate,
    subsidiary: Optional[str] = Query('US', description="Subsidiary for the subscriptions"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Bulk add/update subscriptions for multiple plans in a specific subsidiary."""
    count = await db.bulk_update_subscriptions(
        user.user_id,
        data.plan_codes,
        subsidiary.upper(),
        data.notify_on_available
    )
    return {"status": "ok", "updated": count}


# ============ User Notification History ============

@app.get("/api/me/notifications", response_model=List[UserNotificationHistory])
async def get_my_notifications(
    limit: int = Query(50, ge=1, le=500),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get current user's notification history."""
    return await db.get_user_notification_history(user.user_id, limit)


# ============ API Keys Endpoints ============

@app.get("/api/me/api-keys", response_model=List[ApiKeyInfo])
async def get_my_api_keys(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's API keys."""
    return await db.get_user_api_keys(user.user_id)


@app.post("/api/me/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    data: ApiKeyCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Create a new API key."""
    from datetime import datetime, timedelta, timezone
    
    api_key, key_hash = generate_api_key()
    expires_at = None
    if data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=data.expires_in_days)
    
    key_id = await db.create_api_key(user.user_id, key_hash, data.name, expires_at)
    
    return ApiKeyResponse(
        id=key_id,
        name=data.name,
        api_key=api_key,  # Only returned on creation!
        created_at=datetime.now(timezone.utc),
        expires_at=expires_at
    )


@app.delete("/api/me/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Revoke an API key."""
    success = await db.revoke_api_key(user.user_id, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "ok"}


# ============ Public Config Endpoints ============

# Mapping of subsidiary codes to display info
SUBSIDIARY_INFO = {
    'US': {'name': 'OVHcloud US', 'domain': 'us.ovhcloud.com', 'flag': '🇺🇸', 'region': 'United States'},
    'CA': {'name': 'OVHcloud Canada', 'domain': 'ca.ovhcloud.com', 'flag': '🇨🇦', 'region': 'Canada'},
    'FR': {'name': 'OVHcloud France', 'domain': 'www.ovhcloud.com/fr', 'flag': '🇫🇷', 'region': 'France'},
    'DE': {'name': 'OVHcloud Germany', 'domain': 'www.ovhcloud.com/de', 'flag': '🇩🇪', 'region': 'Germany'},
    'ES': {'name': 'OVHcloud Spain', 'domain': 'www.ovhcloud.com/es-es', 'flag': '🇪🇸', 'region': 'Spain'},
    'IT': {'name': 'OVHcloud Italy', 'domain': 'www.ovhcloud.com/it', 'flag': '🇮🇹', 'region': 'Italy'},
    'NL': {'name': 'OVHcloud Netherlands', 'domain': 'www.ovhcloud.com/nl', 'flag': '🇳🇱', 'region': 'Netherlands'},
    'PL': {'name': 'OVHcloud Poland', 'domain': 'www.ovhcloud.com/pl', 'flag': '🇵🇱', 'region': 'Poland'},
    'PT': {'name': 'OVHcloud Portugal', 'domain': 'www.ovhcloud.com/pt', 'flag': '🇵🇹', 'region': 'Portugal'},
    'GB': {'name': 'OVHcloud UK', 'domain': 'www.ovhcloud.com/en-gb', 'flag': '🇬🇧', 'region': 'United Kingdom'},
    'IE': {'name': 'OVHcloud Ireland', 'domain': 'www.ovhcloud.com/en-ie', 'flag': '🇮🇪', 'region': 'Ireland'},
    'SG': {'name': 'OVHcloud Singapore', 'domain': 'www.ovhcloud.com/en-sg', 'flag': '🇸🇬', 'region': 'Singapore'},
    'AU': {'name': 'OVHcloud Australia', 'domain': 'www.ovhcloud.com/en-au', 'flag': '🇦🇺', 'region': 'Australia'},
    'IN': {'name': 'OVHcloud India', 'domain': 'www.ovhcloud.com/en-in', 'flag': '🇮🇳', 'region': 'India'},
    'WS': {'name': 'OVHcloud International', 'domain': 'www.ovhcloud.com/en', 'flag': '🌍', 'region': 'International'},
}

@app.get("/api/subsidiary")
async def get_subsidiary_info():
    """Get the configured OVH subsidiary info for display in the UI."""
    subsidiary = await db.get_config("ovh_subsidiary") or "US"
    subsidiary = subsidiary.upper()
    info = SUBSIDIARY_INFO.get(subsidiary, SUBSIDIARY_INFO['US'])
    return {
        "code": subsidiary,
        "name": info['name'],
        "domain": info['domain'],
        "flag": info['flag'],
        "region": info['region']
    }

@app.get("/api/subsidiaries")
async def list_subsidiaries():
    """List all available OVH subsidiaries."""
    return [
        {"code": code, **info}
        for code, info in SUBSIDIARY_INFO.items()
    ]


# ============ Config Endpoints (Admin Only) ============

@app.put("/api/config/subsidiary")
async def update_subsidiary(
    request: dict,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update the OVH subsidiary. Requires admin access."""
    code = request.get("code", "").upper()
    if code not in SUBSIDIARY_INFO:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid subsidiary code. Valid codes: {', '.join(SUBSIDIARY_INFO.keys())}"
        )
    await db.set_config("ovh_subsidiary", code)
    return {"status": "ok", "subsidiary": SUBSIDIARY_INFO[code]}

@app.get("/api/config")
async def get_config(admin: AuthenticatedUser = Depends(get_current_admin)):
    """Get all configuration values. Requires admin access."""
    config = await db.get_all_config()
    # Mask the webhook URL for security
    if "discord_webhook_url" in config and config["discord_webhook_url"]:
        url = config["discord_webhook_url"]
        if len(url) > 20:
            config["discord_webhook_url_masked"] = url[:20] + "..." + url[-10:]
        else:
            config["discord_webhook_url_masked"] = "***configured***"
    return config


@app.put("/api/config")
async def update_config(
    config: ConfigUpdate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update a configuration value. Requires admin access."""
    await db.set_config(config.key, config.value)
    return {"status": "ok", "key": config.key}


@app.put("/api/config/discord-webhook")
async def update_discord_webhook(
    config: DiscordWebhookConfig,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update default Discord webhook URL. Requires admin access."""
    await db.set_config("discord_webhook_url", config.webhook_url)
    return {"status": "ok", "message": "Discord webhook URL updated"}


@app.post("/api/config/discord-webhook/test", response_model=TestWebhookResponse)
async def test_discord_webhook(admin: AuthenticatedUser = Depends(get_current_admin)):
    """Test the configured default Discord webhook. Requires admin access."""
    webhook_url = await db.get_config("discord_webhook_url")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="Discord webhook URL not configured")
    
    success, message = await send_test_notification(webhook_url)
    
    # Save to notification history
    await db.save_notification(
        plan_code="TEST",
        datacenter="TEST",
        message="Test notification",
        success=success,
        error_message=None if success else message
    )
    
    return TestWebhookResponse(success=success, message=message)


# ============ Admin User Management Endpoints ============

@app.get("/api/admin/users")
async def admin_get_users(admin: AuthenticatedUser = Depends(get_current_admin)):
    """Get all users. Requires admin access."""
    users = await db.get_all_users()
    return users


@app.get("/api/admin/users/{user_id}")
async def admin_get_user(
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get detailed user info. Requires admin access."""
    user = await db.admin_get_user_details(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(
    user_id: int,
    is_active: Optional[bool] = None,
    is_admin: Optional[bool] = None,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update user status. Requires admin access."""
    # Prevent admin from demoting themselves
    if user_id == admin.user_id and is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove your own admin status")
    
    success = await db.admin_update_user(user_id, is_active=is_active, is_admin=is_admin)
    if not success:
        raise HTTPException(status_code=404, detail="User not found or no changes made")
    return {"status": "ok", "message": "User updated"}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Delete a user. Requires admin access."""
    # Prevent admin from deleting themselves
    if user_id == admin.user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    success = await db.admin_delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "message": "User deleted"}


@app.post("/api/admin/users")
async def admin_create_user(
    user_data: AdminUserCreate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Create a new user. Requires admin access."""
    # Hash the password
    hashed_password = hash_password(user_data.password)
    
    try:
        user_id = await db.admin_create_user(
            email=user_data.email,
            username=user_data.username,
            password_hash=hashed_password,
            is_active=user_data.is_active,
            is_admin=user_data.is_admin
        )
        return {"status": "ok", "user_id": user_id, "message": "User created successfully"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="Email or username already exists")
        raise HTTPException(status_code=400, detail=str(e))


# ============ Admin Settings Endpoints ============

@app.get("/api/admin/settings/registration")
async def admin_get_registration_setting(
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get registration enabled status. Requires admin access."""
    allow_registration = await db.get_config("allow_registration")
    return {"allow_registration": allow_registration == "true"}


@app.put("/api/admin/settings/registration")
async def admin_toggle_registration(
    settings: RegistrationToggle,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Enable or disable public registration. Requires admin access."""
    await db.set_config("allow_registration", "true" if settings.allow_registration else "false")
    return {"status": "ok", "allow_registration": settings.allow_registration}


# ============ Admin Group Management Endpoints ============

@app.get("/api/admin/groups")
async def admin_get_groups(
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get all groups. Requires admin access."""
    groups = await db.get_all_groups()
    return groups


@app.post("/api/admin/groups")
async def admin_create_group(
    group_data: GroupCreate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Create a new group. Requires admin access."""
    try:
        group_id = await db.create_group(
            name=group_data.name,
            description=group_data.description,
            created_by=admin.user_id
        )
        return {"status": "ok", "group_id": group_id, "message": "Group created successfully"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="Group name already exists")
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/admin/groups/{group_id}")
async def admin_get_group(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get group details. Requires admin access."""
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@app.put("/api/admin/groups/{group_id}")
async def admin_update_group(
    group_id: int,
    group_data: GroupUpdate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update a group. Requires admin access."""
    success = await db.update_group(
        group_id=group_id,
        name=group_data.name,
        description=group_data.description
    )
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "ok", "message": "Group updated"}


@app.delete("/api/admin/groups/{group_id}")
async def admin_delete_group(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Delete a group. Requires admin access."""
    success = await db.delete_group(group_id)
    if not success:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"status": "ok", "message": "Group deleted"}


@app.get("/api/admin/groups/{group_id}/members")
async def admin_get_group_members(
    group_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Get all members of a group. Requires admin access."""
    # Verify group exists
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    members = await db.get_group_members(group_id)
    return members


@app.post("/api/admin/groups/{group_id}/members")
async def admin_add_group_member(
    group_id: int,
    member_data: GroupMemberAdd,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Add a user to a group. Requires admin access."""
    # Verify group exists
    group = await db.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    
    try:
        await db.add_group_member(
            group_id=group_id,
            user_id=member_data.user_id,
            role=member_data.role
        )
        return {"status": "ok", "message": "Member added to group"}
    except Exception as e:
        if "duplicate key" in str(e).lower():
            raise HTTPException(status_code=400, detail="User is already a member of this group")
        if "foreign key" in str(e).lower():
            raise HTTPException(status_code=400, detail="User not found")
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/admin/groups/{group_id}/members/{user_id}")
async def admin_remove_group_member(
    group_id: int,
    user_id: int,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Remove a user from a group. Requires admin access."""
    success = await db.remove_group_member(group_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Member not found in group")
    return {"status": "ok", "message": "Member removed from group"}


# ============ User Groups Endpoints (for regular users) ============

@app.get("/api/me/groups")
async def get_my_groups(
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get groups the current user belongs to."""
    groups = await db.get_user_groups(user.user_id)
    return groups


# ============ Plans Endpoints ============

@app.get("/api/plans")
async def get_plans(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get all monitored plans, optionally filtered by subsidiary."""
    plans = await db.get_monitored_plans(subsidiary.upper() if subsidiary else None)
    return plans


@app.post("/api/plans")
async def add_plan(plan: MonitoredPlanCreate):
    """Add a new monitored plan."""
    try:
        subsidiary = getattr(plan, 'subsidiary', 'US')
        plan_id = await db.add_monitored_plan(plan.plan_code, plan.display_name, plan.url, subsidiary)
        return {"status": "ok", "id": plan_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/plans/{plan_code}")
async def update_plan(
    plan_code: str, 
    update: MonitoredPlanUpdate,
    subsidiary: Optional[str] = Query(None, description="Subsidiary to update (or all if omitted)")
):
    """Enable or disable a monitored plan."""
    await db.update_monitored_plan(plan_code, update.enabled, subsidiary.upper() if subsidiary else None)
    return {"status": "ok"}


@app.delete("/api/plans/{plan_code}")
async def delete_plan(
    plan_code: str,
    subsidiary: Optional[str] = Query(None, description="Subsidiary to delete (or all if omitted)")
):
    """Delete a monitored plan."""
    await db.delete_monitored_plan(plan_code, subsidiary.upper() if subsidiary else None)
    return {"status": "ok"}


# ============ Subsidiaries Endpoints ============

@app.get("/api/subsidiaries")
async def get_subsidiaries():
    """Get all active subsidiaries (configured for monitoring)."""
    active = await db.get_active_subsidiaries()
    with_data = await db.get_subsidiaries_with_data()
    
    # Subsidiary display names
    names = {
        'US': 'United States',
        'CA': 'Canada',
        'FR': 'France',
        'DE': 'Germany',
        'GB': 'United Kingdom',
        'ES': 'Spain',
        'IT': 'Italy',
        'NL': 'Netherlands',
        'PL': 'Poland',
        'PT': 'Portugal',
        'IE': 'Ireland',
        'AU': 'Australia',
        'SG': 'Singapore',
        'ASIA': 'Asia Pacific',
        'IN': 'India',
        'WE': 'Western Europe',
        'WS': 'World/International'
    }
    
    return {
        "active": active,
        "with_data": with_data,
        "names": names
    }


# ============ Status Endpoints ============

@app.get("/api/status", response_model=List[InventoryStatus])
async def get_current_status(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get current inventory status for all plans/datacenters, optionally filtered by subsidiary."""
    status = await db.get_current_status(subsidiary.upper() if subsidiary else None)
    return status


@app.get("/api/status/history", response_model=List[StatusHistory])
async def get_status_history(
    plan_code: Optional[str] = Query(None, description="Filter by plan code"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get status history (requires authentication)."""
    history = await db.get_status_history(plan_code, limit)
    return history


# ============ Pricing Endpoints ============

@app.get("/api/pricing/{plan_code}")
async def get_plan_pricing(
    plan_code: str,
    subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")
):
    """Get all pricing tiers for a plan, optionally filtered by subsidiary."""
    pricing = await db.get_plan_pricing(plan_code, subsidiary.upper() if subsidiary else None)
    return pricing


@app.get("/api/pricing")
async def get_pricing_info():
    """Get pricing metadata."""
    last_updated = await db.get_pricing_last_updated()
    return {
        "last_updated": last_updated,
        "source": "OVH Catalog API",
        "update_frequency": "daily"
    }


# ============ Notifications Endpoints ============

@app.get("/api/notifications", response_model=List[NotificationHistory])
async def get_notifications(
    limit: int = Query(50, ge=1, le=500, description="Number of records to return"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get notification history (requires authentication)."""
    notifications = await db.get_notification_history(limit)
    return notifications


# ============ Datacenter Locations ============

@app.get("/api/datacenters")
async def get_datacenters(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get datacenter location mappings, optionally filtered by subsidiary."""
    locations = await db.get_datacenter_locations(subsidiary.upper() if subsidiary else None)
    return locations


# ============ Health Check ============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test database connection
        await db.get_config("discord_webhook_url")
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


# ============ Static Files (Frontend) ============

# Serve static files from frontend directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def serve_frontend():
        """Serve the frontend."""
        return FileResponse(os.path.join(static_dir, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
