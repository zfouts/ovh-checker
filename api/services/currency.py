"""Currency conversion service using live exchange rates."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
import aiohttp

logger = logging.getLogger(__name__)

# Cache for exchange rates
_rate_cache: Dict[str, Tuple[float, datetime]] = {}
_cache_duration = timedelta(hours=1)  # Refresh rates every hour

# Fallback rates (approximate, used if API fails)
FALLBACK_RATES = {
    'EUR_USD': 1.09,  # 1 EUR = 1.09 USD
    'USD_EUR': 0.92,  # 1 USD = 0.92 EUR
    'GBP_USD': 1.27,
    'USD_GBP': 0.79,
    'CAD_USD': 0.74,
    'USD_CAD': 1.35,
}

# Free exchange rate API (no key required)
EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/{base}"


async def fetch_exchange_rate(from_currency: str, to_currency: str) -> float:
    """
    Fetch the current exchange rate from from_currency to to_currency.
    
    Uses exchangerate-api.com (free tier, no API key required).
    Falls back to cached/default rates on error.
    """
    cache_key = f"{from_currency}_{to_currency}"
    
    # Check cache first
    if cache_key in _rate_cache:
        rate, cached_at = _rate_cache[cache_key]
        if datetime.now(timezone.utc) - cached_at < _cache_duration:
            return rate
    
    try:
        async with aiohttp.ClientSession() as session:
            url = EXCHANGE_API_URL.format(base=from_currency.upper())
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rates = data.get('rates', {})
                    rate = rates.get(to_currency.upper())
                    if rate:
                        _rate_cache[cache_key] = (rate, datetime.now(timezone.utc))
                        logger.info(f"Fetched exchange rate: 1 {from_currency} = {rate} {to_currency}")
                        return rate
    except Exception as e:
        logger.warning(f"Failed to fetch exchange rate: {e}")
    
    # Use fallback
    fallback = FALLBACK_RATES.get(cache_key)
    if fallback:
        logger.info(f"Using fallback exchange rate: 1 {from_currency} = {fallback} {to_currency}")
        return fallback
    
    # If no fallback, try inverse
    inverse_key = f"{to_currency}_{from_currency}"
    if inverse_key in FALLBACK_RATES:
        return 1 / FALLBACK_RATES[inverse_key]
    
    # Last resort - assume 1:1
    logger.warning(f"No exchange rate found for {from_currency} to {to_currency}, using 1.0")
    return 1.0


async def convert_price(
    amount: float,
    from_currency: str,
    to_currency: str
) -> float:
    """Convert an amount from one currency to another."""
    if from_currency.upper() == to_currency.upper():
        return amount
    
    rate = await fetch_exchange_rate(from_currency, to_currency)
    return amount * rate


async def get_usd_eur_rate() -> float:
    """Get USD to EUR exchange rate."""
    return await fetch_exchange_rate('USD', 'EUR')


async def get_eur_usd_rate() -> float:
    """Get EUR to USD exchange rate."""
    return await fetch_exchange_rate('EUR', 'USD')


def calculate_price_difference(
    us_price: Optional[float],
    global_price: Optional[float],
    global_price_usd: Optional[float]
) -> Optional[Dict]:
    """
    Calculate the price difference between US and Global prices.
    
    Returns a dict with:
    - difference: absolute difference (positive means US is more expensive)
    - difference_percent: percentage difference
    - cheaper_region: 'US' or 'Global'
    """
    if us_price is None or global_price_usd is None:
        return None
    
    if us_price == 0 and global_price_usd == 0:
        return {
            'difference': 0,
            'difference_percent': 0,
            'cheaper_region': None,
            'us_price_usd': us_price,
            'global_price_eur': global_price,
            'global_price_usd': global_price_usd
        }
    
    difference = us_price - global_price_usd
    
    # Calculate percentage based on the cheaper price
    base_price = min(us_price, global_price_usd) if min(us_price, global_price_usd) > 0 else max(us_price, global_price_usd)
    if base_price > 0:
        difference_percent = (abs(difference) / base_price) * 100
    else:
        difference_percent = 0
    
    return {
        'difference': round(difference, 2),
        'difference_percent': round(difference_percent, 1),
        'cheaper_region': 'Global' if difference > 0 else ('US' if difference < 0 else None),
        'us_price_usd': round(us_price, 2),
        'global_price_eur': round(global_price, 2) if global_price else None,
        'global_price_usd': round(global_price_usd, 2)
    }


class CurrencyConverter:
    """Async-friendly currency converter with caching."""
    
    def __init__(self):
        self._eur_usd_rate: Optional[float] = None
        self._rate_updated: Optional[datetime] = None
        self._refresh_interval = timedelta(hours=1)
    
    async def refresh_rates(self):
        """Refresh exchange rates from API."""
        self._eur_usd_rate = await get_eur_usd_rate()
        self._rate_updated = datetime.now(timezone.utc)
    
    async def get_eur_to_usd_rate(self) -> float:
        """Get cached EUR to USD rate, refreshing if needed."""
        if (self._eur_usd_rate is None or 
            self._rate_updated is None or
            datetime.now(timezone.utc) - self._rate_updated > self._refresh_interval):
            await self.refresh_rates()
        return self._eur_usd_rate or FALLBACK_RATES['EUR_USD']
    
    async def eur_to_usd(self, amount: float) -> float:
        """Convert EUR to USD."""
        rate = await self.get_eur_to_usd_rate()
        return amount * rate
    
    def get_rate_info(self) -> Dict:
        """Get info about current rate."""
        return {
            'eur_usd_rate': self._eur_usd_rate,
            'last_updated': self._rate_updated.isoformat() if self._rate_updated else None,
            'source': 'exchangerate-api.com'
        }


# Global converter instance
converter = CurrencyConverter()
