"""User profile and personal data endpoints (/api/me/*)."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from auth import (
    AuthenticatedUser,
    get_current_user,
    hash_password,
    verify_password,
    generate_api_key,
)
from db_instance import db
from models import (
    UserProfile,
    UserProfileUpdate,
    PasswordChange,
    UserWebhookCreate,
    UserWebhookUpdate,
    UserWebhook,
    PlanSubscriptionCreate,
    PlanSubscriptionUpdate,
    PlanSubscription,
    BulkSubscriptionUpdate,
    ApiKeyCreate,
    ApiKeyResponse,
    ApiKeyInfo,
    TestWebhookResponse,
    UserNotificationHistory
)
from discord_client import send_test_notification

router = APIRouter(prefix="/api/me", tags=["user"])


# ============ Profile Endpoints ============

@router.get("", response_model=UserProfile)
async def get_profile(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's profile."""
    profile = await db.get_user_by_id(user.user_id)
    if not profile:
        raise HTTPException(status_code=404, detail="User not found")
    return profile


@router.put("")
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


@router.post("/password")
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


# ============ Webhooks Endpoints ============

@router.get("/webhooks", response_model=List[UserWebhook])
async def get_my_webhooks(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's webhooks (Discord and Slack)."""
    webhooks = await db.get_user_webhooks(user.user_id)
    # Mask webhook URLs for security
    for wh in webhooks:
        url = wh["webhook_url"]
        if len(url) > 40:
            wh["webhook_url_masked"] = url[:30] + "..." + url[-10:]
        else:
            wh["webhook_url_masked"] = "***configured***"
    return webhooks


@router.post("/webhooks", response_model=UserWebhook)
async def create_my_webhook(
    webhook: UserWebhookCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Create a new webhook (Discord or Slack) for current user with customization options."""
    from discord_client import detect_webhook_type
    
    # Auto-detect webhook type if not provided
    webhook_type = webhook.webhook_type
    if not webhook_type:
        webhook_type = detect_webhook_type(webhook.webhook_url)
        if webhook_type == 'unknown':
            raise HTTPException(status_code=400, detail="Could not detect webhook type. Use a Discord or Slack webhook URL.")
    
    webhook_id = await db.create_user_webhook(
        user_id=user.user_id, 
        webhook_url=webhook.webhook_url, 
        webhook_name=webhook.webhook_name,
        webhook_type=webhook_type,
        bot_username=webhook.bot_username,
        avatar_url=webhook.avatar_url,
        include_price=webhook.include_price,
        include_specs=webhook.include_specs,
        mention_role_id=webhook.mention_role_id,
        embed_color=webhook.embed_color,
        slack_channel=webhook.slack_channel
    )
    return await db.get_user_webhook(user.user_id, webhook_id)


@router.put("/webhooks/{webhook_id}")
async def update_my_webhook(
    webhook_id: int,
    update: UserWebhookUpdate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Update a webhook with customization options."""
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
        slack_channel=update.slack_channel,
        is_active=update.is_active
    )
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "ok"}


@router.delete("/webhooks/{webhook_id}")
async def delete_my_webhook(
    webhook_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Delete a Discord webhook."""
    success = await db.delete_user_webhook(user.user_id, webhook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"status": "ok"}


@router.post("/webhooks/{webhook_id}/test", response_model=TestWebhookResponse)
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


# ============ Subscriptions Endpoints ============

@router.get("/subscriptions", response_model=List[PlanSubscription])
async def get_my_subscriptions(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's plan subscriptions."""
    return await db.get_user_subscriptions(user.user_id)


@router.post("/subscriptions")
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


@router.put("/subscriptions/{plan_code}")
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


@router.delete("/subscriptions/{plan_code}")
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


@router.post("/subscriptions/bulk")
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


# ============ Notifications Endpoints ============

@router.get("/notifications", response_model=List[UserNotificationHistory])
async def get_my_notifications(
    limit: int = Query(50, ge=1, le=500),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get current user's notification history."""
    return await db.get_user_notification_history(user.user_id, limit)


# ============ API Keys Endpoints ============

@router.get("/api-keys", response_model=List[ApiKeyInfo])
async def get_my_api_keys(user: AuthenticatedUser = Depends(get_current_user)):
    """Get current user's API keys."""
    return await db.get_user_api_keys(user.user_id)


@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    data: ApiKeyCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Create a new API key."""
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


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Revoke an API key."""
    success = await db.revoke_api_key(user.user_id, key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "ok"}


# ============ Groups Endpoints ============

@router.get("/groups")
async def get_my_groups(user: AuthenticatedUser = Depends(get_current_user)):
    """Get groups the current user belongs to."""
    groups = await db.get_user_groups(user.user_id)
    return groups
