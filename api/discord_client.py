import aiohttp
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


async def send_test_notification(webhook_url: str) -> tuple[bool, str]:
    """
    Send a test Discord webhook notification.
    
    Returns:
        Tuple of (success, message)
    """
    if not webhook_url:
        return False, "Discord webhook URL not provided"

    embed = {
        "title": "🧪 Test Notification",
        "description": "This is a test notification from OVH Inventory Checker",
        "color": 3447003,  # Blue
        "fields": [
            {"name": "Status", "value": "✅ Webhook is working correctly!", "inline": False},
            {"name": "Timestamp", "value": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": False}
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "OVH Inventory Checker - Test Message"}
    }

    payload = {
        "username": "OVH Stock Alert",
        "embeds": [embed]
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if response.status in (200, 204):
                    logger.info("Test Discord notification sent successfully")
                    return True, "Test notification sent successfully!"
                else:
                    error_text = await response.text()
                    error_msg = f"Discord API returned {response.status}: {error_text}"
                    logger.error(error_msg)
                    return False, error_msg
    except aiohttp.ClientError as e:
        error_msg = f"Failed to connect to Discord: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Failed to send test notification: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
