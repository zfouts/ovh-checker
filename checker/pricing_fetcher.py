import aiohttp
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from catalog_fetcher import get_catalog_url

logger = logging.getLogger(__name__)

MICROCENTS_DIVISOR = 100_000_000  # OVH prices are in microcents


class PricingFetcher:
    def __init__(self, db):
        self.db = db

    async def fetch_catalog(self) -> Optional[Dict[str, Any]]:
        """Fetch the VPS catalog from OVH API."""
        try:
            # Get subsidiary from config (US, FR, CA, etc.), default to US
            subsidiary = await self.db.get_config("ovh_subsidiary") or "US"
            catalog_url = get_catalog_url(subsidiary)
            logger.info(f"Fetching catalog for subsidiary: {subsidiary}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(catalog_url, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Fetched catalog with {len(data.get('plans', []))} plans")
                        return data
                    else:
                        logger.error(f"OVH Catalog API returned {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching catalog: {e}")
            return None

    def extract_pricing(self, plan_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract pricing info from a plan's data.
        Returns a list of pricing tiers (different commitment levels).
        """
        results = []
        plan_code = plan_data.get("planCode", "")
        pricings = plan_data.get("pricings", [])

        for pricing in pricings:
            capacities = pricing.get("capacities", [])
            
            # We only care about renewal pricing (what you actually pay monthly)
            if "renew" not in capacities:
                continue

            commitment = pricing.get("commitment", 0)
            price_microcents = pricing.get("price", 0)
            interval = pricing.get("interval", 1)
            interval_unit = pricing.get("intervalUnit", "month")
            description = pricing.get("description", "")

            # Skip if price is 0 or negative
            if price_microcents <= 0:
                continue

            # Calculate monthly price if interval is not monthly
            if interval_unit == "month" and interval > 1:
                # Total price for interval, divide to get monthly
                price_microcents = price_microcents // interval

            results.append({
                "plan_code": plan_code,
                "commitment_months": commitment,
                "price_microcents": price_microcents,
                "description": description
            })

        return results

    async def update_pricing(self) -> bool:
        """
        Fetch catalog and update pricing for all monitored plans.
        Returns True if successful.
        """
        logger.info("Starting pricing update...")
        
        catalog = await self.fetch_catalog()
        if not catalog:
            logger.error("Failed to fetch catalog")
            return False

        # Get monitored plan codes
        monitored_plans = await self.db.get_monitored_plans()
        monitored_codes = {p["plan_code"] for p in monitored_plans}
        logger.info(f"Updating pricing for {len(monitored_codes)} monitored plans")

        plans = catalog.get("plans", [])
        updated_count = 0
        
        for plan_data in plans:
            plan_code = plan_data.get("planCode", "")
            
            # Only process plans we're monitoring
            if plan_code not in monitored_codes:
                continue

            pricing_tiers = self.extract_pricing(plan_data)
            
            for tier in pricing_tiers:
                try:
                    await self.db.save_pricing(
                        plan_code=tier["plan_code"],
                        commitment_months=tier["commitment_months"],
                        price_microcents=tier["price_microcents"],
                        description=tier["description"]
                    )
                    updated_count += 1
                except Exception as e:
                    logger.error(f"Error saving pricing for {plan_code}: {e}")

        # Update last pricing update timestamp
        await self.db.set_config(
            "pricing_last_updated",
            datetime.now(timezone.utc).isoformat()
        )

        logger.info(f"Pricing update complete. Updated {updated_count} pricing entries.")
        return True

    async def should_update_pricing(self) -> bool:
        """Check if pricing should be updated (once per day)."""
        last_updated = await self.db.get_config("pricing_last_updated")
        
        if not last_updated:
            return True
        
        try:
            last_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            hours_since_update = (now - last_dt).total_seconds() / 3600
            
            # Update if more than 24 hours have passed
            return hours_since_update >= 24
        except Exception as e:
            logger.error(f"Error parsing last update time: {e}")
            return True


def microcents_to_price_string(microcents: int, currency: str = "USD") -> str:
    """Convert microcents to a formatted price string."""
    dollars = microcents / MICROCENTS_DIVISOR
    if currency == "USD":
        return f"${dollars:.2f}/mo"
    return f"{dollars:.2f} {currency}/mo"
