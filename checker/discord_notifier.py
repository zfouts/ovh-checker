import aiohttp
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from catalog_fetcher import get_purchase_url, get_subsidiary_name, DEFAULT_SUBSIDIARY

logger = logging.getLogger(__name__)


async def send_discord_notification(
    webhook_url: str,
    plan_code: str,
    datacenter: str,
    out_of_stock_minutes: int,
    is_test: bool = False,
    plan_info: Optional[Dict[str, Any]] = None,
    user_info: Optional[Dict[str, Any]] = None,
    subsidiary: str = 'US'
) -> Tuple[bool, Optional[str]]:
    """Send a Discord webhook notification."""
    if not webhook_url:
        return False, "Discord webhook URL not configured"

    if is_test:
        embed = {
            "title": "Test Notification",
            "description": "This is a test notification from OVH Inventory Checker",
            "color": 3447003,
            "fields": [
                {"name": "Status", "value": "Webhook is working correctly!", "inline": False}
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        display_name = plan_info.get("display_name", plan_code) if plan_info else plan_code
        price = plan_info.get("price", "N/A") if plan_info else "N/A"
        default_purchase_url = get_purchase_url(subsidiary)
        purchase_url = plan_info.get("purchase_url", default_purchase_url) if plan_info else default_purchase_url
        subsidiary_name = get_subsidiary_name(subsidiary)
        
        embed = {
            "title": f"🟢 VPS Back in Stock! ({subsidiary})",
            "description": f"**{display_name}** is now available in {subsidiary_name}!",
            "color": 5763719,
            "fields": [
                {"name": "Plan", "value": plan_code, "inline": True},
                {"name": "Datacenter", "value": datacenter, "inline": True},
                {"name": "Region", "value": subsidiary_name, "inline": True},
                {"name": "Price", "value": price, "inline": True},
                {"name": "Out of Stock Duration", "value": f"{out_of_stock_minutes} minutes", "inline": True},
                {"name": "Order Now", "value": f"[Click here to order]({purchase_url})", "inline": False}
            ],
            "timestamp": datetime.utcnow().isoformat(),
            "footer": {"text": f"OVH Inventory Checker • {subsidiary_name}"}
        }
        
        # Add user-specific info if this is a personalized notification
        if user_info and user_info.get("webhook_name"):
            embed["footer"]["text"] = f"OVH Inventory Checker • {user_info['webhook_name']} • {subsidiary_name}"

    payload = {
        "username": "OVH Stock Alert",
        "embeds": [embed]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status in (200, 204):
                    logger.info(f"[{subsidiary}] Discord notification sent for {plan_code}/{datacenter}")
                    return True, None
                else:
                    error_text = await response.text()
                    error_msg = f"Discord API returned {response.status}: {error_text}"
                    logger.error(error_msg)
                    return False, error_msg
    except Exception as e:
        error_msg = f"Failed to send Discord notification: {str(e)}"
        logger.error(error_msg)
        return False, error_msg


async def send_notifications_to_all(
    db,
    plan_code: str,
    datacenter: str,
    out_of_stock_minutes: int,
    plan_info: Optional[Dict[str, Any]] = None,
    subsidiary: str = 'US'
) -> Dict[str, Any]:
    """
    Send notifications to:
    1. Default system webhook (if configured)
    2. All users subscribed to this plan
    
    Returns a summary of notification results.
    """
    results = {
        "default_webhook": {"sent": False, "success": False, "error": None},
        "user_webhooks": []
    }
    
    # 1. Send to default system webhook
    default_webhook_url = await db.get_config("discord_webhook_url")
    if default_webhook_url:
        success, error = await send_discord_notification(
            default_webhook_url,
            plan_code,
            datacenter,
            out_of_stock_minutes,
            plan_info=plan_info,
            subsidiary=subsidiary
        )
        results["default_webhook"] = {"sent": True, "success": success, "error": error}
        
        # Save to notification history (system notification)
        await db.save_notification(
            plan_code,
            datacenter,
            f"Back in stock after {out_of_stock_minutes} minutes (default webhook)",
            success,
            error,
            subsidiary=subsidiary
        )
        
        # Also save to user_notification_history as default
        await db.save_user_notification(
            plan_code=plan_code,
            datacenter=datacenter,
            message=f"Back in stock after {out_of_stock_minutes} minutes",
            success=success,
            error_message=error,
            is_default_webhook=True
        )
    
    # 2. Send to all users subscribed to this plan in this subsidiary
    subscribed_users = await db.get_users_subscribed_to_plan(plan_code, subsidiary)
    
    for user in subscribed_users:
        user_info = {
            "user_id": user["user_id"],
            "webhook_id": user["webhook_id"],
            "webhook_name": user.get("webhook_name", "Personal Alert")
        }
        
        success, error = await send_discord_notification(
            user["webhook_url"],
            plan_code,
            datacenter,
            out_of_stock_minutes,
            plan_info=plan_info,
            user_info=user_info,
            subsidiary=subsidiary
        )
        
        results["user_webhooks"].append({
            "user_id": user["user_id"],
            "webhook_id": user["webhook_id"],
            "success": success,
            "error": error
        })
        
        # Save to user notification history
        await db.save_user_notification(
            plan_code=plan_code,
            datacenter=datacenter,
            message=f"Back in stock after {out_of_stock_minutes} minutes",
            success=success,
            error_message=error,
            user_id=user["user_id"],
            webhook_id=user["webhook_id"],
            is_default_webhook=False
        )
        
        logger.info(f"[{subsidiary}] User notification {'sent' if success else 'failed'} for user {user['user_id']}: {plan_code}/{datacenter}")
    
    return results
