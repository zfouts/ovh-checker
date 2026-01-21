"""Plans, status, and subsidiary endpoints."""
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, Query

from auth import (
    AuthenticatedUser,
    get_current_user,
    get_current_admin,
)
from db_instance import db
from models import (
    MonitoredPlanCreate,
    MonitoredPlanUpdate,
    InventoryStatus,
    StatusHistory,
    NotificationHistory,
    ConfigUpdate,
    DiscordWebhookConfig,
    TestWebhookResponse,
)
from discord_client import send_test_notification

router = APIRouter(tags=["plans"])

# Mapping of subsidiary codes to display info
# FR is used as "Global" for all non-US regions
SUBSIDIARY_INFO = {
    'US': {'name': 'OVHcloud US', 'domain': 'us.ovhcloud.com', 'flag': '🇺🇸', 'region': 'United States'},
    'FR': {'name': 'Global (OVHcloud)', 'domain': 'www.ovhcloud.com', 'flag': '🌍', 'region': 'Global'},
}


# ============ Subsidiary Info ============

@router.get("/api/subsidiary")
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


@router.get("/api/subsidiaries/all")
async def list_all_subsidiaries():
    """List all available OVH subsidiaries (for admin dropdown)."""
    return [
        {"code": code, **info}
        for code, info in SUBSIDIARY_INFO.items()
    ]


@router.put("/api/config/subsidiary")
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


@router.get("/api/subsidiaries")
async def get_subsidiaries():
    """Get all active subsidiaries (configured for monitoring).
    
    Only US and Global (FR) are active.
    FR is used as "Global" representing all non-US regions.
    """
    active = await db.get_active_subsidiaries()
    with_data = await db.get_subsidiaries_with_data()
    
    # Filter to only US and FR (Global)
    active = [s for s in active if s in ('US', 'FR')]
    with_data = [s for s in with_data if s in ('US', 'FR')]
    
    # Subsidiary display names - FR is shown as "Global"
    names = {
        'US': 'United States',
        'FR': 'Global',  # FR represents all non-US regions
    }
    
    return {
        "active": active,
        "with_data": with_data,
        "names": names
    }


# ============ Config Endpoints ============

@router.get("/api/config")
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


@router.put("/api/config")
async def update_config(
    config: ConfigUpdate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update a configuration value. Requires admin access."""
    await db.set_config(config.key, config.value)
    return {"status": "ok", "key": config.key}


@router.put("/api/config/discord-webhook")
async def update_discord_webhook(
    config: DiscordWebhookConfig,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Update default Discord webhook URL. Requires admin access."""
    await db.set_config("discord_webhook_url", config.webhook_url)
    return {"status": "ok", "message": "Discord webhook URL updated"}


@router.post("/api/config/discord-webhook/test", response_model=TestWebhookResponse)
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


# ============ Plans ============

@router.get("/api/plans")
async def get_plans(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get all monitored plans, optionally filtered by subsidiary."""
    plans = await db.get_monitored_plans(subsidiary.upper() if subsidiary else None)
    return plans


@router.post("/api/plans")
async def add_plan(
    plan: MonitoredPlanCreate,
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Add a new monitored plan (admin only)."""
    try:
        subsidiary = getattr(plan, 'subsidiary', 'US')
        plan_id = await db.add_monitored_plan(plan.plan_code, plan.display_name, plan.url, subsidiary)
        return {"status": "ok", "id": plan_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/api/plans/{plan_code}")
async def update_plan(
    plan_code: str, 
    update: MonitoredPlanUpdate,
    subsidiary: Optional[str] = Query(None, description="Subsidiary to update (or all if omitted)"),
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Enable or disable a monitored plan (admin only)."""
    await db.update_monitored_plan(plan_code, update.enabled, subsidiary.upper() if subsidiary else None)
    return {"status": "ok"}


@router.delete("/api/plans/{plan_code}")
async def delete_plan(
    plan_code: str,
    subsidiary: Optional[str] = Query(None, description="Subsidiary to delete (or all if omitted)"),
    admin: AuthenticatedUser = Depends(get_current_admin)
):
    """Delete a monitored plan (admin only)."""
    await db.delete_monitored_plan(plan_code, subsidiary.upper() if subsidiary else None)
    return {"status": "ok"}


# ============ Status ============

@router.get("/api/status", response_model=List[InventoryStatus])
async def get_current_status(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get current inventory status for all plans/datacenters, optionally filtered by subsidiary."""
    status = await db.get_current_status(subsidiary.upper() if subsidiary else None)
    return status


@router.get("/api/status/history", response_model=List[StatusHistory])
async def get_status_history(
    plan_code: Optional[str] = Query(None, description="Filter by plan code"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get status history (requires authentication)."""
    history = await db.get_status_history(plan_code, limit)
    return history


# ============ Pricing ============

@router.get("/api/pricing/{plan_code}")
async def get_plan_pricing(
    plan_code: str,
    subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")
):
    """Get all pricing tiers for a plan, optionally filtered by subsidiary."""
    pricing = await db.get_plan_pricing(plan_code, subsidiary.upper() if subsidiary else None)
    return pricing


@router.get("/api/pricing")
async def get_pricing_info():
    """Get pricing metadata."""
    last_updated = await db.get_pricing_last_updated()
    return {
        "last_updated": last_updated,
        "source": "OVH Catalog API",
        "update_frequency": "daily"
    }


# ============ Notifications ============

@router.get("/api/notifications", response_model=List[NotificationHistory])
async def get_notifications(
    limit: int = Query(50, ge=1, le=500, description="Number of records to return"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Get notification history (requires authentication)."""
    notifications = await db.get_notification_history(limit)
    return notifications


# ============ Datacenters ============

@router.get("/api/datacenters")
async def get_datacenters(subsidiary: Optional[str] = Query(None, description="Filter by subsidiary (e.g., US, FR, DE)")):
    """Get datacenter location mappings, optionally filtered by subsidiary."""
    locations = await db.get_datacenter_locations(subsidiary.upper() if subsidiary else None)
    return locations
