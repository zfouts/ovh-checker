"""
Unified notification client supporting Discord and Slack webhooks.
"""
import aiohttp
import ipaddress
import logging
import socket
from typing import Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address is private, loopback, or otherwise internal."""
    try:
        ip = ipaddress.ip_address(ip_str)
        return (
            ip.is_private or
            ip.is_loopback or
            ip.is_reserved or
            ip.is_link_local or
            ip.is_multicast or
            (hasattr(ip, 'is_global') and not ip.is_global)
        )
    except ValueError:
        # If it's not a valid IP, reject it
        return True


def _resolve_and_validate_host(hostname: str) -> Tuple[bool, str]:
    """
    Resolve hostname and validate that it doesn't point to internal IPs.
    Returns (is_safe, error_message).
    """
    try:
        # Resolve all IPs for the hostname
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in results:
            ip_str = sockaddr[0]
            if _is_private_ip(ip_str):
                return False, f"Webhook URL resolves to private/internal IP: {ip_str}"
        return True, ""
    except socket.gaierror as e:
        return False, f"Failed to resolve webhook hostname: {e}"


class WebhookNotifier:
    """Unified webhook notifier for Discord and Slack."""
    
    DISCORD_HOSTS = ('discord.com', 'discordapp.com')
    SLACK_HOSTS = ('hooks.slack.com',)
    
    @staticmethod
    def detect_webhook_type(url: str) -> str:
        """Detect webhook type from URL."""
        if not url:
            return 'unknown'
        url_lower = url.lower()
        if any(host in url_lower for host in WebhookNotifier.DISCORD_HOSTS):
            return 'discord'
        elif any(host in url_lower for host in WebhookNotifier.SLACK_HOSTS):
            return 'slack'
        return 'unknown'
    
    @staticmethod
    def validate_webhook_url(url: str, webhook_type: str = None) -> Tuple[bool, str]:
        """Validate webhook URL format and check for SSRF vulnerabilities."""
        if not url:
            return False, "Webhook URL is required"
        
        if not url.startswith('https://'):
            return False, "Webhook URL must use HTTPS"
        
        detected_type = WebhookNotifier.detect_webhook_type(url)
        
        if webhook_type and detected_type != webhook_type:
            return False, f"URL does not match webhook type '{webhook_type}'"
        
        if detected_type == 'unknown':
            return False, "URL must be a valid Discord or Slack webhook URL"
        
        # SSRF Protection: Validate that the URL doesn't resolve to internal IPs
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            if not hostname:
                return False, "Invalid webhook URL: no hostname"
            
            is_safe, error_msg = _resolve_and_validate_host(hostname)
            if not is_safe:
                logger.warning(f"SSRF protection blocked webhook URL: {error_msg}")
                return False, f"Invalid webhook URL: {error_msg}"
        except Exception as e:
            logger.error(f"Error validating webhook URL: {e}")
            return False, f"Failed to validate webhook URL: {str(e)}"
        
        return True, detected_type

    @staticmethod
    async def send_test_notification(
        webhook_url: str,
        webhook_type: Optional[str] = None,
        bot_username: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Send a test notification to verify webhook is working."""
        if not webhook_type:
            webhook_type = WebhookNotifier.detect_webhook_type(webhook_url)
        
        if webhook_type == 'discord':
            return await WebhookNotifier._send_discord_test(webhook_url, bot_username)
        elif webhook_type == 'slack':
            return await WebhookNotifier._send_slack_test(webhook_url, bot_username)
        else:
            return False, f"Unknown webhook type: {webhook_type}"

    @staticmethod
    async def send_stock_notification(
        webhook_url: str,
        webhook_type: str,
        plan_code: str,
        datacenter: str,
        out_of_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: Optional[str] = None,
        webhook_name: Optional[str] = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send a stock notification."""
        if webhook_type == 'discord':
            return await WebhookNotifier._send_discord_notification(
                webhook_url, plan_code, datacenter, out_of_stock_minutes,
                plan_info, subsidiary, bot_username, webhook_name, **kwargs
            )
        elif webhook_type == 'slack':
            return await WebhookNotifier._send_slack_notification(
                webhook_url, plan_code, datacenter, out_of_stock_minutes,
                plan_info, subsidiary, bot_username, webhook_name, **kwargs
            )
        else:
            return False, f"Unknown webhook type: {webhook_type}"

    @staticmethod
    async def send_out_of_stock_notification(
        webhook_url: str,
        webhook_type: str,
        plan_code: str,
        datacenter: str,
        in_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: str = None,
        webhook_name: str = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send an out-of-stock notification."""
        if webhook_type == 'discord':
            return await WebhookNotifier._send_discord_out_of_stock(
                webhook_url, plan_code, datacenter, in_stock_minutes,
                plan_info, subsidiary, bot_username, webhook_name, **kwargs
            )
        elif webhook_type == 'slack':
            return await WebhookNotifier._send_slack_out_of_stock(
                webhook_url, plan_code, datacenter, in_stock_minutes,
                plan_info, subsidiary, bot_username, webhook_name, **kwargs
            )
        else:
            return False, f"Unknown webhook type: {webhook_type}"

    # ========== Discord Implementation ==========
    
    @staticmethod
    async def _send_discord_test(webhook_url: str, bot_username: str = None) -> Tuple[bool, str]:
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
            "username": bot_username or "OVH Stock Alert",
            "embeds": [embed]
        }

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Discord")

    @staticmethod
    async def _send_discord_notification(
        webhook_url: str,
        plan_code: str,
        datacenter: str,
        out_of_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: str = None,
        webhook_name: str = None,
        mention_role_id: str = None,
        embed_color: str = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send a Discord stock notification."""
        from catalog_fetcher import get_purchase_url, get_subsidiary_name
        
        display_name = plan_info.get("display_name", plan_code) if plan_info else plan_code
        price = plan_info.get("price", "N/A") if plan_info else "N/A"
        purchase_url = plan_info.get("purchase_url", get_purchase_url(subsidiary)) if plan_info else get_purchase_url(subsidiary)
        subsidiary_name = get_subsidiary_name(subsidiary)
        
        # Parse embed color
        color = 5763719  # Default green
        if embed_color:
            try:
                color = int(embed_color.lstrip('#'), 16)
            except ValueError:
                pass
        
        embed = {
            "title": f"🟢 VPS Back in Stock! ({subsidiary})",
            "description": f"**{display_name}** is now available in {subsidiary_name}!",
            "color": color,
            "fields": [
                {"name": "Plan", "value": plan_code, "inline": True},
                {"name": "Datacenter", "value": datacenter, "inline": True},
                {"name": "Region", "value": subsidiary_name, "inline": True},
                {"name": "Price", "value": price, "inline": True},
                {"name": "Out of Stock Duration", "value": f"{out_of_stock_minutes} minutes", "inline": True},
                {"name": "Order Now", "value": f"[Click here to order]({purchase_url})", "inline": False}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": f"OVH Inventory Checker • {webhook_name or subsidiary_name}"}
        }

        content = None
        if mention_role_id:
            content = f"<@&{mention_role_id}>"

        payload = {
            "username": bot_username or "OVH Stock Alert",
            "embeds": [embed]
        }
        if content:
            payload["content"] = content

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Discord")

    @staticmethod
    async def _send_discord_out_of_stock(
        webhook_url: str,
        plan_code: str,
        datacenter: str,
        in_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: str = None,
        webhook_name: str = None,
        mention_role_id: str = None,
        embed_color: str = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send a Discord out-of-stock notification."""
        from catalog_fetcher import get_subsidiary_name
        
        display_name = plan_info.get("display_name", plan_code) if plan_info else plan_code
        subsidiary_name = get_subsidiary_name(subsidiary)
        
        # Use red/orange color for out of stock
        color = 15158332  # Default red
        if embed_color:
            try:
                color = int(embed_color.lstrip('#'), 16)
            except ValueError:
                pass
        
        embed = {
            "title": f"🔴 VPS Out of Stock ({subsidiary})",
            "description": f"**{display_name}** is no longer available in {subsidiary_name}.",
            "color": color,
            "fields": [
                {"name": "Plan", "value": plan_code, "inline": True},
                {"name": "Datacenter", "value": datacenter, "inline": True},
                {"name": "Region", "value": subsidiary_name, "inline": True},
                {"name": "Was In Stock For", "value": f"{in_stock_minutes} minutes", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "footer": {"text": f"OVH Inventory Checker • {webhook_name or subsidiary_name}"}
        }

        content = None
        if mention_role_id:
            content = f"<@&{mention_role_id}>"

        payload = {
            "username": bot_username or "OVH Stock Alert",
            "embeds": [embed]
        }
        if content:
            payload["content"] = content

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Discord")

    # ========== Slack Implementation ==========
    
    @staticmethod
    async def _send_slack_test(webhook_url: str, bot_username: str = None) -> Tuple[bool, str]:
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
            "text": "Test Notification from OVH Inventory Checker"  # Fallback text
        }
        if bot_username:
            payload["username"] = bot_username

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Slack")

    @staticmethod
    async def _send_slack_notification(
        webhook_url: str,
        plan_code: str,
        datacenter: str,
        out_of_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: str = None,
        webhook_name: str = None,
        slack_channel: str = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send a Slack stock notification."""
        from catalog_fetcher import get_purchase_url, get_subsidiary_name
        
        display_name = plan_info.get("display_name", plan_code) if plan_info else plan_code
        price = plan_info.get("price", "N/A") if plan_info else "N/A"
        purchase_url = plan_info.get("purchase_url", get_purchase_url(subsidiary)) if plan_info else get_purchase_url(subsidiary)
        subsidiary_name = get_subsidiary_name(subsidiary)
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🟢 VPS Back in Stock! ({subsidiary})",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{display_name}* is now available in {subsidiary_name}!"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Plan:*\n{plan_code}"},
                    {"type": "mrkdwn", "text": f"*Datacenter:*\n{datacenter}"},
                    {"type": "mrkdwn", "text": f"*Region:*\n{subsidiary_name}"},
                    {"type": "mrkdwn", "text": f"*Price:*\n{price}"},
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"⏱️ Out of stock for *{out_of_stock_minutes} minutes*"
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "🛒 Order Now",
                            "emoji": True
                        },
                        "url": purchase_url,
                        "style": "primary"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"OVH Inventory Checker • {webhook_name or subsidiary_name} • <!date^{int(datetime.now(timezone.utc).timestamp())}^{{date_short_pretty}} at {{time}}|{datetime.now(timezone.utc).isoformat()}>"
                    }
                ]
            }
        ]

        payload = {
            "blocks": blocks,
            "text": f"🟢 {display_name} is back in stock in {subsidiary_name}!"  # Fallback
        }
        if bot_username:
            payload["username"] = bot_username
        if slack_channel:
            payload["channel"] = slack_channel

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Slack")

    @staticmethod
    async def _send_slack_out_of_stock(
        webhook_url: str,
        plan_code: str,
        datacenter: str,
        in_stock_minutes: int,
        plan_info: Optional[Dict[str, Any]] = None,
        subsidiary: str = 'US',
        bot_username: str = None,
        webhook_name: str = None,
        slack_channel: str = None,
        **kwargs
    ) -> Tuple[bool, Optional[str]]:
        """Send a Slack out-of-stock notification."""
        from catalog_fetcher import get_subsidiary_name
        
        display_name = plan_info.get("display_name", plan_code) if plan_info else plan_code
        subsidiary_name = get_subsidiary_name(subsidiary)
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔴 VPS Out of Stock ({subsidiary})",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{display_name}* is no longer available in {subsidiary_name}."
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Plan:*\n{plan_code}"},
                    {"type": "mrkdwn", "text": f"*Datacenter:*\n{datacenter}"},
                    {"type": "mrkdwn", "text": f"*Region:*\n{subsidiary_name}"},
                    {"type": "mrkdwn", "text": f"*Was In Stock For:*\n{in_stock_minutes} minutes"},
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"OVH Inventory Checker • {webhook_name or subsidiary_name} • <!date^{int(datetime.now(timezone.utc).timestamp())}^{{date_short_pretty}} at {{time}}|{datetime.now(timezone.utc).isoformat()}>"
                    }
                ]
            }
        ]

        payload = {
            "blocks": blocks,
            "text": f"🔴 {display_name} is out of stock in {subsidiary_name}!"  # Fallback
        }
        if bot_username:
            payload["username"] = bot_username
        if slack_channel:
            payload["channel"] = slack_channel

        return await WebhookNotifier._post_webhook(webhook_url, payload, "Slack")

    # ========== Common HTTP Posting ==========
    
    @staticmethod
    async def _post_webhook(url: str, payload: Dict, service_name: str) -> Tuple[bool, str]:
        """Post payload to webhook URL."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status in (200, 204):
                        logger.info(f"{service_name} notification sent successfully")
                        return True, f"{service_name} notification sent successfully!"
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
            error_msg = f"Failed to send {service_name} notification: {str(e)}"
            logger.error(error_msg)
            return False, error_msg


# Convenience functions for backwards compatibility
async def send_test_notification(webhook_url: str, webhook_type: str = None) -> Tuple[bool, str]:
    """Send a test notification (auto-detects type if not provided)."""
    return await WebhookNotifier.send_test_notification(webhook_url, webhook_type)
