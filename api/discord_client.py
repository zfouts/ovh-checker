"""
Webhook notification client for API.
Supports Discord and Slack webhooks.
"""
import aiohttp
import logging
from typing import Optional, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def detect_webhook_type(url: str) -> str:
    """Detect webhook type from URL."""
    if not url:
        return 'unknown'
    url_lower = url.lower()
    if 'discord.com' in url_lower or 'discordapp.com' in url_lower:
        return 'discord'
    elif 'hooks.slack.com' in url_lower:
        return 'slack'
    return 'unknown'


async def send_test_notification(webhook_url: str, webhook_type: str = None) -> tuple[bool, str]:
    """
    Send a test webhook notification (Discord or Slack).
    
    Returns:
        Tuple of (success, message)
    """
    if not webhook_url:
        return False, "Webhook URL not provided"

    if not webhook_type:
        webhook_type = detect_webhook_type(webhook_url)

    if webhook_type == 'discord':
        return await _send_discord_test(webhook_url)
    elif webhook_type == 'slack':
        return await _send_slack_test(webhook_url)
    else:
        return False, f"Unknown webhook type. URL must be a Discord or Slack webhook."


async def _send_discord_test(webhook_url: str) -> tuple[bool, str]:
    """Send a test Discord notification."""
    embed = {
        "title": "🧪 Test Notification",
        "description": "This is a test notification from OVH Inventory Checker",
        "color": 3447003,  # Blue
        "fields": [
            {"name": "Status", "value": "✅ Webhook is working correctly!", "inline": False},
            {"name": "Timestamp", "value": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"), "inline": False}
        ],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {"text": "OVH Inventory Checker - Test Message"}
    }

    payload = {
        "username": "OVH Stock Alert",
        "embeds": [embed]
    }

    return await _post_webhook(webhook_url, payload, "Discord")


async def _send_slack_test(webhook_url: str) -> tuple[bool, str]:
    """Send a test Slack notification."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🧪 Test Notification",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "This is a test notification from *OVH Inventory Checker*"
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*Status:*\n✅ Webhook is working correctly!"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Timestamp:*\n{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "OVH Inventory Checker - Test Message"
                }
            ]
        }
    ]

    payload = {
        "blocks": blocks,
        "text": "Test Notification from OVH Inventory Checker"
    }

    return await _post_webhook(webhook_url, payload, "Slack")


async def _post_webhook(url: str, payload: dict, service_name: str) -> tuple[bool, str]:
    """Post payload to webhook URL."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            ) as response:
                if response.status in (200, 204):
                    logger.info(f"Test {service_name} notification sent successfully")
                    return True, f"Test notification sent successfully to {service_name}!"
                else:
                    error_text = await response.text()
                    error_msg = f"{service_name} API returned {response.status}: {error_text}"
                    logger.error(error_msg)
                    return False, error_msg
    except aiohttp.ClientError as e:
        error_msg = f"Failed to connect to {service_name}: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Failed to send test notification: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
