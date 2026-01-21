"""
Catalog Fetcher - Discovers VPS plans from OVH Order Catalog API

Supports multiple OVH subsidiaries:
- US: https://us.ovhcloud.com/engine/api/v1/order/catalog/public/vps?ovhSubsidiary=US
- FR: https://www.ovhcloud.com/eu/engine/api/v1/order/catalog/public/vps?ovhSubsidiary=FR
- CA: https://ca.ovhcloud.com/engine/api/v1/order/catalog/public/vps?ovhSubsidiary=CA
- etc.

This API provides:
- All available plan codes
- Plan specifications (CPU, RAM, Storage, Bandwidth)
- Invoice names
- Pricing with commitment tiers
- Available datacenters per plan
"""

import aiohttp
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Subsidiary to base URL mapping
# Note: European subsidiaries use the /eu/ path on www.ovhcloud.com
SUBSIDIARY_URLS = {
    # Americas - have their own domains
    'US': 'https://us.ovhcloud.com',
    'CA': 'https://ca.ovhcloud.com',
    # Europe - all use www.ovhcloud.com/eu/ for the API
    'FR': 'https://www.ovhcloud.com/eu',
    'DE': 'https://www.ovhcloud.com/eu',
    'ES': 'https://www.ovhcloud.com/eu',
    'IT': 'https://www.ovhcloud.com/eu',
    'NL': 'https://www.ovhcloud.com/eu',
    'PL': 'https://www.ovhcloud.com/eu',
    'PT': 'https://www.ovhcloud.com/eu',
    'GB': 'https://www.ovhcloud.com/eu',
    'IE': 'https://www.ovhcloud.com/eu',
    # Asia Pacific - use www.ovhcloud.com/asia/
    'SG': 'https://www.ovhcloud.com/asia',
    'AU': 'https://www.ovhcloud.com/asia',
    'IN': 'https://www.ovhcloud.com/asia',
    # Other
    'WS': 'https://www.ovhcloud.com/en',  # World/International
}

# Localized website URLs for purchase links (different from API base)
SUBSIDIARY_WEBSITE_URLS = {
    'US': 'https://us.ovhcloud.com',
    'CA': 'https://ca.ovhcloud.com',
    'FR': 'https://www.ovhcloud.com/fr',
    'DE': 'https://www.ovhcloud.com/de',
    'ES': 'https://www.ovhcloud.com/es-es',
    'IT': 'https://www.ovhcloud.com/it',
    'NL': 'https://www.ovhcloud.com/nl',
    'PL': 'https://www.ovhcloud.com/pl',
    'PT': 'https://www.ovhcloud.com/pt',
    'GB': 'https://www.ovhcloud.com/en-gb',
    'IE': 'https://www.ovhcloud.com/en-ie',
    'SG': 'https://www.ovhcloud.com/en-sg',
    'AU': 'https://www.ovhcloud.com/en-au',
    'IN': 'https://www.ovhcloud.com/en-in',
    'WS': 'https://www.ovhcloud.com/en',
}

DEFAULT_SUBSIDIARY = 'US'

# Comprehensive datacenter code to location mapping
# Maps lowercase datacenter codes to display names, cities, and countries
DATACENTER_LOCATIONS = {
    # US Regions - Main
    'us-east-vin': {'display_name': 'Virginia', 'city': 'Vint Hill', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-west-hil': {'display_name': 'Oregon', 'city': 'Hillsboro', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    # US Local Zones
    'us-east-lz-atl': {'display_name': 'Atlanta', 'city': 'Atlanta', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-east-lz-dal': {'display_name': 'Dallas', 'city': 'Dallas', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-east-lz-mia': {'display_name': 'Miami', 'city': 'Miami', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-east-lz-nyc': {'display_name': 'New York', 'city': 'New York', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-west-lz-den': {'display_name': 'Denver', 'city': 'Denver', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-west-lz-lax': {'display_name': 'Los Angeles', 'city': 'Los Angeles', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-west-lz-pao': {'display_name': 'Palo Alto', 'city': 'Palo Alto', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    'us-west-lz-sea': {'display_name': 'Seattle', 'city': 'Seattle', 'country': 'United States', 'country_code': 'US', 'flag': '🇺🇸', 'region': 'US'},
    # Canada
    'ca-east-bhs': {'display_name': 'Beauharnois', 'city': 'Beauharnois', 'country': 'Canada', 'country_code': 'CA', 'flag': '🇨🇦', 'region': 'CA'},
    # Europe - Main
    'eu-west-gra': {'display_name': 'Gravelines', 'city': 'Gravelines', 'country': 'France', 'country_code': 'FR', 'flag': '🇫🇷', 'region': 'EU'},
    'eu-west-sbg': {'display_name': 'Strasbourg', 'city': 'Strasbourg', 'country': 'France', 'country_code': 'FR', 'flag': '🇫🇷', 'region': 'EU'},
    'eu-west-lim': {'display_name': 'Frankfurt', 'city': 'Frankfurt', 'country': 'Germany', 'country_code': 'DE', 'flag': '🇩🇪', 'region': 'EU'},
    'eu-west-eri': {'display_name': 'London', 'city': 'London', 'country': 'United Kingdom', 'country_code': 'GB', 'flag': '🇬🇧', 'region': 'EU'},
    'eu-central-waw': {'display_name': 'Warsaw', 'city': 'Warsaw', 'country': 'Poland', 'country_code': 'PL', 'flag': '🇵🇱', 'region': 'EU'},
    'eu-south-mil': {'display_name': 'Milan', 'city': 'Milan', 'country': 'Italy', 'country_code': 'IT', 'flag': '🇮🇹', 'region': 'EU'},
    # Europe Local Zones
    'eu-west-lz-ams': {'display_name': 'Amsterdam', 'city': 'Amsterdam', 'country': 'Netherlands', 'country_code': 'NL', 'flag': '🇳🇱', 'region': 'EU'},
    'eu-west-lz-bru': {'display_name': 'Brussels', 'city': 'Brussels', 'country': 'Belgium', 'country_code': 'BE', 'flag': '🇧🇪', 'region': 'EU'},
    'eu-west-lz-vie': {'display_name': 'Vienna', 'city': 'Vienna', 'country': 'Austria', 'country_code': 'AT', 'flag': '🇦🇹', 'region': 'EU'},
    'eu-west-lz-mrs': {'display_name': 'Marseille', 'city': 'Marseille', 'country': 'France', 'country_code': 'FR', 'flag': '🇫🇷', 'region': 'EU'},
    'eu-west-lz-zrh': {'display_name': 'Zurich', 'city': 'Zurich', 'country': 'Switzerland', 'country_code': 'CH', 'flag': '🇨🇭', 'region': 'EU'},
    'eu-central-lz-prg': {'display_name': 'Prague', 'city': 'Prague', 'country': 'Czech Republic', 'country_code': 'CZ', 'flag': '🇨🇿', 'region': 'EU'},
    'eu-south-lz-mad': {'display_name': 'Madrid', 'city': 'Madrid', 'country': 'Spain', 'country_code': 'ES', 'flag': '🇪🇸', 'region': 'EU'},
    # Asia Pacific
    'ap-south-mum': {'display_name': 'Mumbai', 'city': 'Mumbai', 'country': 'India', 'country_code': 'IN', 'flag': '🇮🇳', 'region': 'APAC'},
    'ap-southeast-sgp': {'display_name': 'Singapore', 'city': 'Singapore', 'country': 'Singapore', 'country_code': 'SG', 'flag': '🇸🇬', 'region': 'APAC'},
    'ap-southeast-syd': {'display_name': 'Sydney', 'city': 'Sydney', 'country': 'Australia', 'country_code': 'AU', 'flag': '🇦🇺', 'region': 'APAC'},
}

def get_datacenter_location(dc_code: str) -> Dict[str, str]:
    """Get location info for a datacenter code."""
    dc_code_lower = dc_code.lower()
    if dc_code_lower in DATACENTER_LOCATIONS:
        return DATACENTER_LOCATIONS[dc_code_lower].copy()
    # Fallback - use the code as display name
    return {
        'display_name': dc_code.upper(),
        'city': dc_code.upper(),
        'country': 'Unknown',
        'country_code': '',
        'flag': '🌐',
        'region': 'OTHER'
    }

def get_catalog_url(subsidiary: str) -> str:
    """Get the catalog API URL for a subsidiary."""
    base = SUBSIDIARY_URLS.get(subsidiary.upper(), SUBSIDIARY_URLS['US'])
    return f"{base}/engine/api/v1/order/catalog/public/vps?ovhSubsidiary={subsidiary.upper()}"

def get_datacenter_api_base(subsidiary: str) -> str:
    """Get the datacenter API base URL for a subsidiary."""
    base = SUBSIDIARY_URLS.get(subsidiary.upper(), SUBSIDIARY_URLS['US'])
    return f"{base}/engine/api/v1/vps/order/rule/datacenter/"

def get_purchase_url(subsidiary: str) -> str:
    """Get the VPS purchase page URL for a subsidiary."""
    base = SUBSIDIARY_WEBSITE_URLS.get(subsidiary.upper(), SUBSIDIARY_WEBSITE_URLS.get('US'))
    return f"{base}/vps/"

def get_subsidiary_name(subsidiary: str) -> str:
    """Get a human-readable name for a subsidiary."""
    names = {
        'US': 'OVHcloud US',
        'CA': 'OVHcloud Canada',
        'FR': 'OVHcloud France',
        'DE': 'OVHcloud Germany',
        'ES': 'OVHcloud Spain',
        'IT': 'OVHcloud Italy',
        'NL': 'OVHcloud Netherlands',
        'PL': 'OVHcloud Poland',
        'PT': 'OVHcloud Portugal',
        'GB': 'OVHcloud UK',
        'IE': 'OVHcloud Ireland',
        'SG': 'OVHcloud Singapore',
        'AU': 'OVHcloud Australia',
        'IN': 'OVHcloud India',
        'WS': 'OVHcloud International',
    }
    return names.get(subsidiary.upper(), f'OVHcloud {subsidiary.upper()}')


@dataclass
class PlanSpec:
    """Specification for a VPS plan."""
    plan_code: str
    invoice_name: str
    description: str
    vcpu: int
    ram_gb: int
    storage_gb: int
    storage_type: str
    bandwidth_mbps: int
    bandwidth_unlimited: bool
    datacenters: List[str]
    # Visibility/orderable info from catalog tags
    is_orderable: bool = True
    visibility_tags: List[str] = None
    # Product line: "2025" for new VPS 1-6, "legacy" for older plans
    product_line: str = "legacy"
    product_range: str = ""


@dataclass
class PlanPricing:
    """Pricing tier for a plan."""
    plan_code: str
    commitment_months: int
    price_microcents: int
    currency: str
    description: str


class CatalogFetcher:
    """Fetches and parses the OVH Order Catalog API."""

    def __init__(self, db, subsidiary: str = 'US'):
        self.db = db
        self.subsidiary = subsidiary.upper()

    async def fetch_catalog(self) -> Optional[Dict[str, Any]]:
        """Fetch the complete VPS catalog from OVH."""
        try:
            catalog_url = get_catalog_url(self.subsidiary)
            logger.info(f"Fetching catalog for subsidiary {self.subsidiary}: {catalog_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(catalog_url, timeout=60) as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"Fetched catalog with {len(data.get('plans', []))} plans")
                        return data
                    else:
                        logger.error(f"Failed to fetch catalog: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error fetching catalog: {e}")
            return None

    def extract_plan_specs(self, catalog: Dict[str, Any]) -> List[PlanSpec]:
        """Extract plan specifications from catalog products.
        
        Includes both orderable plans (with order-funnel:show tag) and internal/bundle plans.
        The is_orderable flag distinguishes between them.
        """
        specs = []
        products = {p['name']: p for p in catalog.get('products', [])}
        
        for plan in catalog.get('plans', []):
            plan_code = plan.get('planCode', '')
            
            # Only process VPS plans (skip non-VPS products)
            if not plan_code.startswith('vps-'):
                continue
            
            # Skip upgrade paths and degressivity plans (promotional bundles)
            if '-vps-2025-' in plan_code or 'degressivity' in plan_code:
                continue
            
            # Get product info
            product_name = plan.get('product', '')
            product = products.get(product_name, {})
            
            if not product:
                # Try to find by plan_code
                product = products.get(plan_code, {})
            
            product_blobs = product.get('blobs', {})
            tech = product_blobs.get('technical', {})
            meta = product_blobs.get('meta', {})
            
            # Extract visibility tags from plan blobs
            plan_blobs = plan.get('blobs', {}) or {}
            visibility_tags = plan_blobs.get('tags', []) or []
            
            # Extract commercial line/range (determines if 2025 vs legacy)
            commercial = plan_blobs.get('commercial', {}) or {}
            product_line = commercial.get('line', 'legacy') or 'legacy'
            product_range = commercial.get('range', '') or ''
            
            # Normalize product_line: "2025" = new plans, everything else = "legacy"
            if product_line != '2025':
                product_line = 'legacy'
            
            # Determine if orderable:
            # - For 2025 line: orderable if has order-funnel:show or empty tags
            # - For legacy line: NOT orderable on main configurator (only via API/special flows)
            if product_line == '2025':
                # 2025 plans: empty tags or order-funnel:show = orderable
                if not visibility_tags:
                    is_orderable = True
                else:
                    is_orderable = 'order-funnel:show' in visibility_tags
            else:
                # Legacy plans: not orderable on main website configurator
                is_orderable = False
            
            # Extract specs
            cpu = tech.get('cpu', {})
            memory = tech.get('memory', {})
            storage = tech.get('storage', {}).get('disks', [{}])[0] if tech.get('storage', {}).get('disks') else {}
            bandwidth = tech.get('bandwidth', {})
            
            # Extract datacenters from plan configurations
            datacenters = []
            for config in plan.get('configurations', []):
                if config.get('name') == 'vps_datacenter':
                    datacenters = config.get('values', [])
                    break
            
            # Also check meta configurations
            if not datacenters:
                for config in meta.get('configurations', []):
                    if config.get('name') == 'vps_datacenter':
                        for val in config.get('values', []):
                            dc = val.get('value', '') if isinstance(val, dict) else val
                            if dc:
                                datacenters.append(dc)
            
            # Determine storage type - LZ plans use NAS, not local NVMe
            if '.LZ' in plan_code:
                storage_type = "NAS (Network)"
            else:
                storage_type = f"{storage.get('technology', '')} ({storage.get('interface', '')})"
            
            spec = PlanSpec(
                plan_code=plan_code,
                invoice_name=plan.get('invoiceName', plan_code),
                description=product.get('description', ''),
                vcpu=cpu.get('cores', 0),
                ram_gb=memory.get('size', 0),
                storage_gb=storage.get('capacity', 0),
                storage_type=storage_type,
                bandwidth_mbps=bandwidth.get('level', 0),
                bandwidth_unlimited=bandwidth.get('unlimited', False),
                datacenters=datacenters,
                is_orderable=is_orderable,
                visibility_tags=visibility_tags,
                product_line=product_line,
                product_range=product_range
            )
            specs.append(spec)
            
        orderable_count = sum(1 for s in specs if s.is_orderable)
        logger.info(f"Extracted specs for {len(specs)} plans ({orderable_count} orderable, {len(specs) - orderable_count} internal/bundle)")
        return specs

    def extract_pricing(self, catalog: Dict[str, Any]) -> List[PlanPricing]:
        """Extract pricing tiers from catalog plans."""
        pricing_list = []
        currency = catalog.get('locale', {}).get('currencyCode', 'USD')
        
        for plan in catalog.get('plans', []):
            plan_code = plan.get('planCode', '')
            
            # Only process VPS plans
            if not plan_code.startswith('vps-'):
                continue
            
            # Skip upgrade paths and degressivity plans
            if '-vps-2025-' in plan_code or 'degressivity' in plan_code:
                continue
            
            # Extract pricing tiers
            for pricing in plan.get('pricings', []):
                # Only look at renewal prices with "default" mode
                if 'renew' not in pricing.get('capacities', []):
                    continue
                if pricing.get('mode') != 'default':
                    continue
                
                commitment = pricing.get('commitment', 0)
                price = pricing.get('price', 0)
                description = pricing.get('description', '')
                
                pricing_item = PlanPricing(
                    plan_code=plan_code,
                    commitment_months=commitment,
                    price_microcents=price,
                    currency=currency,
                    description=description
                )
                pricing_list.append(pricing_item)
        
        logger.info(f"Extracted {len(pricing_list)} pricing entries")
        return pricing_list

    def extract_datacenter_locations(self, catalog: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
        """Extract datacenter locations (city, country) from catalog products.
        
        Returns dict keyed by datacenter display name (e.g., "US-WEST-OR") with location info.
        """
        locations = {}
        
        # Country code to flag emoji mapping
        country_flags = {
            'United States': ('US', '🇺🇸', 'US'),
            'Canada': ('CA', '🇨🇦', 'CA'),
            'France': ('FR', '🇫🇷', 'EU'),
            'Germany': ('DE', '🇩🇪', 'EU'),
            'United Kingdom': ('GB', '🇬🇧', 'EU'),
            'Netherlands': ('NL', '🇳🇱', 'EU'),
            'Belgium': ('BE', '🇧🇪', 'EU'),
            'Poland': ('PL', '🇵🇱', 'EU'),
            'Spain': ('ES', '🇪🇸', 'EU'),
            'Italy': ('IT', '🇮🇹', 'EU'),
            'Austria': ('AT', '🇦🇹', 'EU'),
            'Switzerland': ('CH', '🇨🇭', 'EU'),
            'Czech Republic': ('CZ', '🇨🇿', 'EU'),
            'India': ('IN', '🇮🇳', 'APAC'),
            'Australia': ('AU', '🇦🇺', 'APAC'),
            'Singapore': ('SG', '🇸🇬', 'APAC'),
            'Japan': ('JP', '🇯🇵', 'APAC'),
        }
        
        for product in catalog.get('products', []):
            blobs = product.get('blobs')
            if not blobs:
                continue
            meta = blobs.get('meta', {})
            
            for config in meta.get('configurations', []):
                if config.get('name') != 'vps_datacenter':
                    continue
                
                for val in config.get('values', []):
                    dc_name = val.get('value', '')  # e.g., "US-WEST-OR"
                    if not dc_name:
                        continue
                    
                    tech = val.get('blobs', {}).get('technical', {}).get('datacenter', {})
                    city = tech.get('city', '')
                    country = tech.get('country', '')
                    
                    if city and country and dc_name not in locations:
                        country_info = country_flags.get(country, ('', '🌐', 'OTHER'))
                        locations[dc_name] = {
                            'city': city,
                            'country': country,
                            'country_code': country_info[0],
                            'flag': country_info[1],
                            'region': country_info[2]
                        }
        
        logger.info(f"Extracted {len(locations)} datacenter locations from catalog")
        return locations

    async def fetch_datacenter_code_mapping(self, plan_code: str) -> Dict[str, str]:
        """Fetch the mapping of datacenter display names to codes from availability API.
        
        Returns dict like {"US-WEST-OR": "us-west-hil", "US-EAST-VA": "us-east-vin"}
        """
        url = self.get_availability_url(plan_code)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=30) as response:
                    if response.status == 200:
                        data = await response.json()
                        mapping = {}
                        for dc in data.get('datacenters', []):
                            dc_name = dc.get('datacenter', '')
                            dc_code = dc.get('code', '')
                            if dc_name and dc_code:
                                mapping[dc_name] = dc_code
                        return mapping
        except Exception as e:
            logger.error(f"Error fetching datacenter code mapping: {e}")
        return {}

    def get_availability_url(self, plan_code: str) -> str:
        """Generate the datacenter availability URL for a plan."""
        api_base = get_datacenter_api_base(self.subsidiary)
        return f"{api_base}?ovhSubsidiary={self.subsidiary}&os=Ubuntu%2025.04&planCode={plan_code}"

    async def discover_and_sync_plans(self) -> Dict[str, Any]:
        """
        Discover all available VPS plans from the catalog and sync to database.
        Also syncs datacenter locations with city/country data.
        Returns summary of discovered plans.
        """
        catalog = await self.fetch_catalog()
        if not catalog:
            return {"error": f"Failed to fetch catalog for {self.subsidiary}"}
        
        # Get purchase URL for this subsidiary
        purchase_url = get_purchase_url(self.subsidiary)
        
        specs = self.extract_plan_specs(catalog)
        pricing = self.extract_pricing(catalog)
        datacenter_locations = self.extract_datacenter_locations(catalog)
        
        # Get datacenter code mappings from a sample of plans to cover all regions
        # Only need a few plans since they share the same datacenter codes
        dc_code_mapping = {}
        sample_plans = [
            'vps-2025-model1',      # US
            'vps-2025-model1-eu',   # EU
            'vps-2025-model1-ca',   # Canada
            'vps-2025-model1.LZ',   # Local Zones US
            'vps-2025-model1.LZ-eu' # Local Zones EU
        ]
        for plan_code in sample_plans:
            mapping = await self.fetch_datacenter_code_mapping(plan_code)
            for dc_name, dc_code in mapping.items():
                if dc_name not in dc_code_mapping:
                    dc_code_mapping[dc_name] = dc_code
        
        logger.info(f"Got {len(dc_code_mapping)} datacenter code mappings from {len(sample_plans)} sample plans")
        
        # Sync to database
        plans_added = 0
        plans_updated = 0
        pricing_updated = 0
        locations_synced = 0
        
        for spec in specs:
            url = self.get_availability_url(spec.plan_code)
            
            # Determine display name - check LZ first since it can have -eu suffix
            display_name = spec.invoice_name
            if '.LZ' in spec.plan_code:
                if '-eu' in spec.plan_code:
                    display_name += ' (EU Local Zone)'
                elif '-ca' in spec.plan_code:
                    display_name += ' (CA Local Zone)'
                else:
                    display_name += ' (Local Zone)'
            elif spec.plan_code.endswith('-eu'):
                display_name += ' (EU)'
            elif spec.plan_code.endswith('-ca'):
                display_name += ' (Canada)'
            
            # Upsert plan with visibility info
            visibility_tags_str = ','.join(spec.visibility_tags) if spec.visibility_tags else None
            result = await self.db.upsert_plan(
                plan_code=spec.plan_code,
                subsidiary=self.subsidiary,
                display_name=display_name,
                url=url,
                purchase_url=purchase_url,
                vcpu=spec.vcpu,
                ram_gb=spec.ram_gb,
                storage_gb=spec.storage_gb,
                storage_type=spec.storage_type,
                bandwidth_mbps=spec.bandwidth_mbps,
                description=spec.description,
                is_orderable=spec.is_orderable,
                visibility_tags=visibility_tags_str,
                product_line=spec.product_line
            )
            if result == 'added':
                plans_added += 1
            elif result == 'updated':
                plans_updated += 1
        
        # Sync pricing
        for p in pricing:
            await self.db.save_pricing(
                plan_code=p.plan_code,
                subsidiary=self.subsidiary,
                commitment_months=p.commitment_months,
                price_microcents=p.price_microcents,
                description=p.description,
                currency=p.currency
            )
            pricing_updated += 1
        
        # Sync datacenter locations using the code mapping
        for dc_name, loc_info in datacenter_locations.items():
            dc_code = dc_code_mapping.get(dc_name)
            if dc_code:
                # Use our comprehensive mapping for accurate location data
                known_location = get_datacenter_location(dc_code)
                await self.db.upsert_datacenter_location(
                    datacenter_code=dc_code,
                    subsidiary=self.subsidiary,
                    display_name=known_location['display_name'],
                    city=known_location['city'],
                    country=known_location['country'],
                    country_code=known_location['country_code'],
                    flag=known_location['flag'],
                    region=known_location['region']
                )
                locations_synced += 1
            else:
                logger.warning(f"No code mapping found for datacenter: {dc_name}")
        
        # Mark plans not in current catalog as discontinued for this subsidiary
        active_plan_codes = [s.plan_code for s in specs]
        plans_discontinued = await self.db.mark_plans_discontinued(active_plan_codes, self.subsidiary)
        if plans_discontinued > 0:
            logger.info(f"Marked {plans_discontinued} plans as discontinued for {self.subsidiary}")
        
        # Mark new plans as active after initial discovery period
        plans_activated = await self.db.mark_new_plans_active()
        if plans_activated > 0:
            logger.info(f"Marked {plans_activated} new plans as active")
        
        # Update last sync time for this subsidiary
        from datetime import datetime, timezone
        await self.db.set_config(f'catalog_last_synced_{self.subsidiary}', datetime.now(timezone.utc).isoformat())
        
        summary = {
            "subsidiary": self.subsidiary,
            "total_plans_in_catalog": len(catalog.get('plans', [])),
            "vps_2025_plans_discovered": len(specs),
            "plans_added": plans_added,
            "plans_updated": plans_updated,
            "plans_discontinued": plans_discontinued,
            "pricing_entries_synced": pricing_updated,
            "datacenter_locations_synced": locations_synced
        }
        
        logger.info(f"Catalog sync complete for {self.subsidiary}: {summary}")
        return summary

    async def should_sync_catalog(self, hours: int = 24) -> bool:
        """Check if catalog should be synced for this subsidiary (default: every 24 hours)."""
        from datetime import datetime, timedelta, timezone
        
        last_synced = await self.db.get_config(f'catalog_last_synced_{self.subsidiary}')
        if not last_synced:
            return True
        
        try:
            last_dt = datetime.fromisoformat(last_synced)
            # Ensure timezone-aware comparison
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) - last_dt > timedelta(hours=hours)
        except ValueError:
            return True
