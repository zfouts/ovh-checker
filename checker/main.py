import aiohttp
import asyncio
import logging
from typing import Dict, Any, List, Optional

from database import Database
from discord_notifier import send_discord_notification, send_notifications_to_all
from pricing_fetcher import PricingFetcher
from catalog_fetcher import get_datacenter_location
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OVHChecker:
    def __init__(self, db: Database, subsidiary: str = 'US'):
        self.db = db
        self.subsidiary = subsidiary

    async def fetch_availability(self, url: str) -> Optional[Dict[str, Any]]:
        """Fetch availability data from OVH API."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data
                    else:
                        logger.error(f"OVH API returned {response.status} for {url}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def parse_availability(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Parse OVH API response to extract datacenter availability.
        OVH returns: {"datacenters": [{"datacenter": "...", "code": "...", "status": "available|out-of-stock", ...}]}
        """
        results = []
        
        if not data:
            return results

        # OVH API returns {"datacenters": [...]}
        datacenters = data.get("datacenters", [])
        
        if isinstance(datacenters, list):
            for dc_info in datacenters:
                if isinstance(dc_info, dict):
                    datacenter = dc_info.get("datacenter", "unknown")
                    datacenter_code = dc_info.get("code", "")
                    linux_status = dc_info.get("linuxStatus", "out-of-stock")
                    
                    # Consider available if Linux status is available
                    is_available = linux_status == "available"
                    
                    results.append({
                        "datacenter": datacenter,
                        "datacenter_code": datacenter_code,
                        "is_available": is_available,
                        "linux_status": linux_status
                    })

        return results

    async def check_plan(self, plan_code: str, url: str):
        """Check availability for a single plan."""
        logger.info(f"[{self.subsidiary}] Checking {plan_code}...")
        
        data = await self.fetch_availability(url)
        if data is None:
            logger.warning(f"[{self.subsidiary}] No data received for {plan_code}")
            return

        availabilities = self.parse_availability(data)
        
        if not availabilities:
            logger.warning(f"[{self.subsidiary}] No datacenters found in response for {plan_code}")
            return

        for avail in availabilities:
            datacenter = avail["datacenter"]
            datacenter_code = avail.get("datacenter_code", "")
            is_available = avail["is_available"]
            linux_status = avail.get("linux_status", "unknown")

            # Ensure datacenter location is stored with proper display name
            if datacenter_code:
                loc = get_datacenter_location(datacenter_code)
                await self.db.upsert_datacenter_location(
                    datacenter_code=datacenter_code,
                    subsidiary=self.subsidiary,
                    display_name=loc['display_name'],
                    city=loc['city'],
                    country=loc['country'],
                    country_code=loc['country_code'],
                    flag=loc['flag'],
                    region=loc['region']
                )

            # Get last known status BEFORE saving the new one
            # (otherwise we'd compare the new status to itself)
            last_status = await self.db.get_last_status(plan_code, datacenter, self.subsidiary)
            was_available = last_status["is_available"] if last_status else None

            # Save current status with subsidiary
            await self.db.save_inventory_status(
                plan_code,
                self.subsidiary,
                datacenter, 
                datacenter_code,
                is_available, 
                linux_status,
                data
            )

            if is_available:
                # Item is in stock now
                if was_available is False:
                    # It was out of stock, now it's back!
                    out_of_stock_minutes = await self.db.mark_returned_to_stock(plan_code, datacenter, self.subsidiary)
                    
                    # Get notification threshold from database (allows dynamic updates)
                    notification_threshold = await get_notification_threshold(self.db)
                    
                    if out_of_stock_minutes and out_of_stock_minutes >= notification_threshold:
                        # Send notifications to default webhook AND all subscribed users
                        plan_info = await self.db.get_plan_info(plan_code, self.subsidiary)
                        
                        results = await send_notifications_to_all(
                            self.db,
                            plan_code,
                            datacenter,
                            out_of_stock_minutes,
                            plan_info=plan_info,
                            subsidiary=self.subsidiary
                        )
                        
                        # Log results
                        default_result = results["default_webhook"]
                        user_count = len(results["user_webhooks"])
                        user_success = sum(1 for u in results["user_webhooks"] if u["success"])
                        
                        logger.info(
                            f"[{self.subsidiary}] NOTIFY: {plan_code}/{datacenter} back in stock after {out_of_stock_minutes} min. "
                            f"Default: {'OK' if default_result['success'] else 'FAIL'}, "
                            f"Users: {user_success}/{user_count} succeeded"
                        )
                    elif out_of_stock_minutes:
                        logger.info(f"[{self.subsidiary}] INFO: {plan_code}/{datacenter} back after {out_of_stock_minutes} min (below threshold)")
            else:
                # Item is out of stock
                await self.db.track_out_of_stock(plan_code, datacenter, self.subsidiary)

    async def run_check_cycle(self):
        """Run a single check cycle for all monitored plans for this subsidiary."""
        plans = await self.db.get_monitored_plans(self.subsidiary)
        
        logger.info(f"[{self.subsidiary}] Checking {len(plans)} plans...")
        
        for plan in plans:
            try:
                await self.check_plan(plan["plan_code"], plan["url"])
            except Exception as e:
                logger.error(f"[{self.subsidiary}] Error checking {plan['plan_code']}: {e}")
            
            await asyncio.sleep(1)


async def get_check_interval(db: Database) -> int:
    """Get check interval from database, falling back to env/default."""
    try:
        interval = await db.get_config("check_interval_seconds")
        if interval:
            return max(30, min(3600, int(interval)))  # Clamp between 30s and 1h
    except (ValueError, TypeError):
        pass
    return settings.check_interval_seconds


async def get_notification_threshold(db: Database) -> int:
    """Get notification threshold from database, falling back to env/default."""
    try:
        threshold = await db.get_config("notification_threshold_minutes")
        if threshold:
            return max(1, min(1440, int(threshold)))  # Clamp between 1min and 24h
    except (ValueError, TypeError):
        pass
    return settings.notification_threshold_minutes


async def run_single_subsidiary_mode(db: Database, subsidiary: str):
    """
    Run checker for a single subsidiary.
    Used in distributed mode where each agent handles one region.
    """
    from catalog_fetcher import CatalogFetcher
    
    agent_id = settings.agent_id or f"checker-{subsidiary.lower()}"
    logger.info(f"[{agent_id}] Starting single-subsidiary checker for {subsidiary}")
    
    # Initial catalog sync
    catalog_fetcher = CatalogFetcher(db, subsidiary)
    if await catalog_fetcher.should_sync_catalog():
        logger.info(f"[{agent_id}] Syncing plans from OVH Order Catalog API...")
        result = await catalog_fetcher.discover_and_sync_plans()
        logger.info(f"[{agent_id}] Catalog sync result: {result}")
    else:
        logger.info(f"[{agent_id}] Catalog is up to date")
    
    checker = OVHChecker(db, subsidiary)
    
    try:
        while True:
            logger.info(f"[{agent_id}] Starting check cycle for {subsidiary}...")
            await checker.run_check_cycle()
            
            # Check if catalog needs sync (daily)
            if await catalog_fetcher.should_sync_catalog():
                logger.info(f"[{agent_id}] Daily catalog sync triggered...")
                result = await catalog_fetcher.discover_and_sync_plans()
                logger.info(f"[{agent_id}] Catalog sync result: {result}")
            
            # Get current check interval from database (allows dynamic updates)
            check_interval = await get_check_interval(db)
            logger.info(f"[{agent_id}] Check cycle complete. Sleeping for {check_interval}s...")
            await asyncio.sleep(check_interval)
    except asyncio.CancelledError:
        logger.info(f"[{agent_id}] Received shutdown signal")
        raise


async def run_multi_subsidiary_mode(db: Database):
    """
    Run checker for all configured subsidiaries sequentially.
    Legacy mode - all subsidiaries in one process.
    """
    from catalog_fetcher import CatalogFetcher
    
    # Get list of subsidiaries to monitor
    subsidiaries = await db.get_monitored_subsidiaries()
    logger.info(f"Monitoring subsidiaries: {', '.join(subsidiaries)}")

    # Initial catalog sync for all subsidiaries
    logger.info("Checking if catalog sync is needed for any subsidiary...")
    for subsidiary in subsidiaries:
        catalog_fetcher = CatalogFetcher(db, subsidiary)
        if await catalog_fetcher.should_sync_catalog():
            logger.info(f"Syncing plans from OVH Order Catalog API for {subsidiary}...")
            result = await catalog_fetcher.discover_and_sync_plans()
            logger.info(f"Catalog sync result for {subsidiary}: {result}")
        else:
            logger.info(f"Catalog for {subsidiary} is up to date")

    try:
        while True:
            logger.info("Starting check cycle for all subsidiaries...")
            
            # Run check cycle for each subsidiary
            for subsidiary in subsidiaries:
                checker = OVHChecker(db, subsidiary)
                await checker.run_check_cycle()
            
            # Check if catalog needs sync (daily) for each subsidiary
            for subsidiary in subsidiaries:
                catalog_fetcher = CatalogFetcher(db, subsidiary)
                if await catalog_fetcher.should_sync_catalog():
                    logger.info(f"Daily catalog sync triggered for {subsidiary}...")
                    result = await catalog_fetcher.discover_and_sync_plans()
                    logger.info(f"Catalog sync result for {subsidiary}: {result}")
            
            # Get current check interval from database (allows dynamic updates)
            check_interval = await get_check_interval(db)
            logger.info(f"Check cycle complete. Sleeping for {check_interval} seconds...")
            await asyncio.sleep(check_interval)
    except asyncio.CancelledError:
        logger.info("Received shutdown signal")
        raise


async def main():
    # Determine mode based on SUBSIDIARY env var
    if settings.subsidiary:
        mode = f"Single-Subsidiary Mode ({settings.subsidiary})"
    else:
        mode = "Multi-Subsidiary Mode (all regions)"
    
    logger.info(f"Starting OVH Inventory Checker - {mode}")
    
    db = Database(settings.database_url)
    await db.connect()
    logger.info("Connected to database")

    try:
        if settings.subsidiary:
            # Distributed mode: handle single subsidiary
            await run_single_subsidiary_mode(db, settings.subsidiary.upper())
        else:
            # Legacy mode: handle all subsidiaries
            await run_multi_subsidiary_mode(db)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
