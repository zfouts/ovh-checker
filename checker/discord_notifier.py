"""
Discord and Slack notification handler.
Uses the unified WebhookNotifier for actual sending.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from catalog_fetcher import get_purchase_url, get_subsidiary_name, DEFAULT_SUBSIDIARY
from webhook_notifier import WebhookNotifier

logger = logging.getLogger(__name__)


async def send_discord_notification(
    webhook_url: str,
    plan_code: str,
    datacenter: str,
    out_of_stock_minutes: int,
    is_test: bool = False,
    plan_info: Optional[Dict[str, Any]] = None,
    user_info: Optional[Dict[str, Any]] = None,
    subsidiary: str = 'US',
    webhook_type: str = 'discord'
) -> Tuple[bool, Optional[str]]:
    """Send a webhook notification (Discord or Slack)."""
    if not webhook_url:
        return False, "Webhook URL not configured"

    # Auto-detect webhook type if not specified
    if not webhook_type:
        webhook_type = WebhookNotifier.detect_webhook_type(webhook_url)

    if is_test:
        bot_username = user_info.get("bot_username") if user_info else None
        success, message = await WebhookNotifier.send_test_notification(
            webhook_url, webhook_type, bot_username
        )
        return success, None if success else message
    
    # Prepare notification parameters
    kwargs = {}
    if user_info:
        kwargs['bot_username'] = user_info.get('bot_username')
        kwargs['webhook_name'] = user_info.get('webhook_name', 'Personal Alert')
        kwargs['mention_role_id'] = user_info.get('mention_role_id')
        kwargs['embed_color'] = user_info.get('embed_color')
        kwargs['slack_channel'] = user_info.get('slack_channel')
    
    success, error = await WebhookNotifier.send_stock_notification(
        webhook_url=webhook_url,
        webhook_type=webhook_type,
        plan_code=plan_code,
        datacenter=datacenter,
        out_of_stock_minutes=out_of_stock_minutes,
        plan_info=plan_info,
        subsidiary=subsidiary,
        **kwargs
    )
    
    if success:
        logger.info(f"[{subsidiary}] {webhook_type.capitalize()} notification sent for {plan_code}/{datacenter}")
    
    return success, error


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
    2. All users subscribed to this plan (supports both Discord and Slack)
    
    Returns a summary of notification results.
    """
    results = {
        "default_webhook": {"sent": False, "success": False, "error": None},
        "user_webhooks": []
    }
    
    # 1. Send to default system webhook (Discord)
    default_webhook_url = await db.get_config("discord_webhook_url")
    if default_webhook_url:
        success, error = await send_discord_notification(
            default_webhook_url,
            plan_code,
            datacenter,
            out_of_stock_minutes,
            plan_info=plan_info,
            subsidiary=subsidiary,
            webhook_type='discord'
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
    
    # 2. Check for default Slack webhook as well
    default_slack_url = await db.get_config("slack_webhook_url")
    if default_slack_url:
        success, error = await send_discord_notification(
            default_slack_url,
            plan_code,
            datacenter,
            out_of_stock_minutes,
            plan_info=plan_info,
            subsidiary=subsidiary,
            webhook_type='slack'
        )
        
        # Save to notification history
        await db.save_user_notification(
            plan_code=plan_code,
            datacenter=datacenter,
            message=f"Back in stock after {out_of_stock_minutes} minutes (Slack)",
            success=success,
            error_message=error,
            is_default_webhook=True
        )
    
    # 3. Send to all users subscribed to this plan in this subsidiary
    subscribed_users = await db.get_users_subscribed_to_plan(plan_code, subsidiary)
    
    for user in subscribed_users:
        # Get webhook type (default to discord for backwards compatibility)
        webhook_type = user.get("webhook_type", "discord")
        
        user_info = {
            "user_id": user["user_id"],
            "webhook_id": user["webhook_id"],
            "webhook_name": user.get("webhook_name", "Personal Alert"),
            "bot_username": user.get("bot_username"),
            "mention_role_id": user.get("mention_role_id"),
            "embed_color": user.get("embed_color"),
            "slack_channel": user.get("slack_channel")
        }
        
        success, error = await send_discord_notification(
            user["webhook_url"],
            plan_code,
            datacenter,
            out_of_stock_minutes,
            plan_info=plan_info,
            user_info=user_info,
            subsidiary=subsidiary,
            webhook_type=webhook_type
        )
        
        results["user_webhooks"].append({
            "user_id": user["user_id"],
            "webhook_id": user["webhook_id"],
            "webhook_type": webhook_type,
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
        
        logger.info(f"[{subsidiary}] User {webhook_type} notification {'sent' if success else 'failed'} for user {user['user_id']}: {plan_code}/{datacenter}")
    
    return results
