"""
SQLAlchemy-based Database Layer for OVH Checker Service

This module provides an async database interface using SQLAlchemy 2.0 ORM.
"""

import os
import sys
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import select, update, delete, func, and_, or_, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

# Add parent directory to path to import shared models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import (
    Base, Config, User, MonitoredPlan, PlanPricing, DatacenterLocation,
    InventoryStatus, OutOfStockTracking, NotificationHistory,
    UserPlanSubscription, UserWebhook, UserNotificationHistory
)


# Currency symbols for formatting
CURRENCY_SYMBOLS = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': 'CA$', 'AUD': 'A$'}


def format_price(price_microcents: int, currency: str = 'USD') -> str:
    """Convert microcents to formatted price string."""
    dollars = price_microcents / 100_000_000
    symbol = CURRENCY_SYMBOLS.get(currency, currency + ' ')
    return f"{symbol}{dollars:.2f}/mo"


class Database:
    """
    SQLAlchemy-based async database interface for the checker service.
    
    This class provides the same public API as the old asyncpg-based implementation
    but uses SQLAlchemy ORM for all database operations.
    """
    
    def __init__(self, database_url: str):
        """
        Initialize database with connection URL.
        
        Args:
            database_url: PostgreSQL connection URL (e.g., postgresql://user:pass@host/db)
        """
        # Convert standard postgresql:// to async postgresql+asyncpg://
        if database_url.startswith('postgresql://'):
            database_url = database_url.replace('postgresql://', 'postgresql+asyncpg://', 1)
        
        self.database_url = database_url
        self.engine = None
        self.session_factory: Optional[async_sessionmaker[AsyncSession]] = None

    async def connect(self):
        """Create database engine and session factory."""
        self.engine = create_async_engine(
            self.database_url,
            echo=os.getenv("DATABASE_ECHO", "false").lower() == "true",
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    async def disconnect(self):
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()

    def _session(self) -> AsyncSession:
        """Create a new session."""
        return self.session_factory()

    # ============ Config ============

    async def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value."""
        async with self._session() as session:
            result = await session.execute(
                select(Config.value).where(Config.key == key)
            )
            return result.scalar_one_or_none()

    async def set_config(self, key: str, value: str):
        """Set a configuration value."""
        async with self._session() as session:
            stmt = pg_insert(Config).values(
                key=key,
                value=value,
                updated_at=func.now()
            ).on_conflict_do_update(
                index_elements=['key'],
                set_={'value': value, 'updated_at': func.now()}
            )
            await session.execute(stmt)
            await session.commit()

    # ============ Plans ============

    async def get_monitored_plans(self, subsidiary: str = None) -> List[Dict[str, Any]]:
        """Get all enabled monitored plans, optionally filtered by subsidiary."""
        async with self._session() as session:
            query = (
                select(
                    MonitoredPlan.plan_code,
                    MonitoredPlan.subsidiary,
                    MonitoredPlan.display_name,
                    MonitoredPlan.url,
                    MonitoredPlan.purchase_url
                )
                .where(MonitoredPlan.enabled == True)
            )
            
            if subsidiary:
                query = query.where(MonitoredPlan.subsidiary == subsidiary)
            
            result = await session.execute(query)
            return [dict(row._mapping) for row in result.all()]

    async def get_monitored_subsidiaries(self) -> List[str]:
        """Get list of subsidiaries to monitor from config."""
        config_val = await self.get_config("monitored_subsidiaries")
        if not config_val:
            return ['US']
        if config_val.upper() == 'ALL':
            return ['US', 'CA', 'FR', 'DE', 'ES', 'IT', 'NL', 'PL', 'PT', 'GB', 'IE', 'SG', 'AU', 'IN', 'WS']
        return [s.strip().upper() for s in config_val.split(',') if s.strip()]

    async def upsert_plan(
        self,
        plan_code: str,
        subsidiary: str,
        display_name: str,
        url: str,
        purchase_url: str,
        vcpu: int = None,
        ram_gb: int = None,
        storage_gb: int = None,
        storage_type: str = None,
        bandwidth_mbps: int = None,
        description: str = None,
        is_orderable: bool = True,
        visibility_tags: str = None,
        product_line: str = 'legacy'
    ) -> str:
        """Insert or update a plan. Returns 'added', 'updated', 'reactivated', or 'unchanged'."""
        async with self._session() as session:
            # Check if exists
            existing = await session.execute(
                select(MonitoredPlan.id, MonitoredPlan.catalog_status)
                .where(and_(
                    MonitoredPlan.plan_code == plan_code,
                    MonitoredPlan.subsidiary == subsidiary
                ))
            )
            row = existing.first()
            
            if row:
                was_discontinued = row.catalog_status == 'discontinued'
                
                # Update specs and mark as seen/active
                await session.execute(
                    update(MonitoredPlan)
                    .where(and_(
                        MonitoredPlan.plan_code == plan_code,
                        MonitoredPlan.subsidiary == subsidiary
                    ))
                    .values(
                        display_name=display_name or MonitoredPlan.display_name,
                        url=url,
                        purchase_url=purchase_url,
                        vcpu=vcpu if vcpu is not None else MonitoredPlan.vcpu,
                        ram_gb=ram_gb if ram_gb is not None else MonitoredPlan.ram_gb,
                        storage_gb=storage_gb if storage_gb is not None else MonitoredPlan.storage_gb,
                        storage_type=storage_type if storage_type is not None else MonitoredPlan.storage_type,
                        bandwidth_mbps=bandwidth_mbps if bandwidth_mbps is not None else MonitoredPlan.bandwidth_mbps,
                        description=description if description is not None else MonitoredPlan.description,
                        is_orderable=is_orderable,
                        visibility_tags=visibility_tags,
                        product_line=product_line,
                        catalog_status='active',
                        last_seen_at=func.now(),
                        discontinued_at=None,
                        updated_at=func.now()
                    )
                )
                await session.commit()
                return 'reactivated' if was_discontinued else 'updated'
            else:
                # Insert new plan
                plan = MonitoredPlan(
                    plan_code=plan_code,
                    subsidiary=subsidiary,
                    display_name=display_name,
                    url=url,
                    purchase_url=purchase_url,
                    vcpu=vcpu,
                    ram_gb=ram_gb,
                    storage_gb=storage_gb,
                    storage_type=storage_type,
                    bandwidth_mbps=bandwidth_mbps,
                    description=description,
                    is_orderable=is_orderable,
                    visibility_tags=visibility_tags,
                    product_line=product_line,
                    enabled=True,
                    catalog_status='new'
                )
                session.add(plan)
                await session.commit()
                return 'added'

    async def mark_plans_discontinued(self, active_plan_codes: list, subsidiary: str) -> int:
        """Mark plans not in the active list as discontinued for a specific subsidiary."""
        async with self._session() as session:
            result = await session.execute(
                update(MonitoredPlan)
                .where(and_(
                    MonitoredPlan.subsidiary == subsidiary,
                    MonitoredPlan.plan_code.notin_(active_plan_codes),
                    MonitoredPlan.catalog_status != 'discontinued'
                ))
                .values(
                    catalog_status='discontinued',
                    discontinued_at=func.now(),
                    updated_at=func.now()
                )
            )
            await session.commit()
            return result.rowcount

    async def mark_new_plans_active(self) -> int:
        """Mark 'new' plans as 'active' after their first sync."""
        async with self._session() as session:
            result = await session.execute(
                update(MonitoredPlan)
                .where(and_(
                    MonitoredPlan.catalog_status == 'new',
                    MonitoredPlan.first_seen_at < text("NOW() - INTERVAL '1 hour'")
                ))
                .values(
                    catalog_status='active',
                    updated_at=func.now()
                )
            )
            await session.commit()
            return result.rowcount

    async def get_plan_info(self, plan_code: str, subsidiary: str = 'US') -> Optional[Dict[str, Any]]:
        """Get plan info by plan code including pricing."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    MonitoredPlan.plan_code,
                    MonitoredPlan.subsidiary,
                    MonitoredPlan.display_name,
                    MonitoredPlan.url,
                    MonitoredPlan.purchase_url,
                    PlanPricing.price_microcents,
                    PlanPricing.commitment_months,
                    PlanPricing.currency
                )
                .outerjoin(PlanPricing, and_(
                    PlanPricing.plan_code == MonitoredPlan.plan_code,
                    PlanPricing.subsidiary == MonitoredPlan.subsidiary,
                    PlanPricing.commitment_months == 0
                ))
                .where(and_(
                    MonitoredPlan.plan_code == plan_code,
                    MonitoredPlan.subsidiary == subsidiary
                ))
            )
            row = result.first()
            
            if row:
                r = dict(row._mapping)
                if r.get('price_microcents'):
                    r['price'] = format_price(r['price_microcents'], r.get('currency', 'USD'))
                else:
                    r['price'] = None
                return r
            return None

    async def save_pricing(
        self,
        plan_code: str,
        subsidiary: str,
        commitment_months: int,
        price_microcents: int,
        description: str = "",
        currency: str = "USD"
    ):
        """Save or update pricing for a plan."""
        async with self._session() as session:
            stmt = pg_insert(PlanPricing).values(
                plan_code=plan_code,
                subsidiary=subsidiary,
                commitment_months=commitment_months,
                price_microcents=price_microcents,
                currency=currency,
                description=description,
                updated_at=func.now()
            ).on_conflict_do_update(
                index_elements=['plan_code', 'subsidiary', 'commitment_months'],
                set_={
                    'price_microcents': price_microcents,
                    'currency': currency,
                    'description': description,
                    'updated_at': func.now()
                }
            )
            await session.execute(stmt)
            await session.commit()

    async def upsert_datacenter_location(
        self,
        datacenter_code: str,
        subsidiary: str,
        display_name: str = "",
        city: str = "",
        country: str = "",
        country_code: str = "",
        flag: str = "🌐",
        region: str = "OTHER"
    ):
        """Insert or update datacenter location info."""
        async with self._session() as session:
            stmt = pg_insert(DatacenterLocation).values(
                datacenter_code=datacenter_code,
                subsidiary=subsidiary,
                display_name=display_name or city,  # Fallback to city if no display_name
                city=city,
                country=country,
                country_code=country_code,
                flag=flag,
                region=region
            ).on_conflict_do_update(
                index_elements=['datacenter_code', 'subsidiary'],
                set_={
                    'display_name': display_name or city,
                    'city': city,
                    'country': country,
                    'country_code': country_code,
                    'flag': flag,
                    'region': region
                }
            )
            await session.execute(stmt)
            await session.commit()

    # ============ Inventory Status ============

    async def save_inventory_status(
        self,
        plan_code: str,
        subsidiary: str,
        datacenter: str,
        datacenter_code: str,
        is_available: bool,
        linux_status: str,
        raw_response: Dict[str, Any]
    ):
        """Save inventory status check result."""
        async with self._session() as session:
            status = InventoryStatus(
                plan_code=plan_code,
                subsidiary=subsidiary,
                datacenter=datacenter,
                datacenter_code=datacenter_code,
                is_available=is_available,
                linux_status=linux_status,
                raw_response=raw_response
            )
            session.add(status)
            await session.commit()

    async def get_last_status(self, plan_code: str, datacenter: str, subsidiary: str = 'US') -> Optional[Dict[str, Any]]:
        """Get the last known status for a plan/datacenter combo."""
        async with self._session() as session:
            result = await session.execute(
                select(InventoryStatus.is_available, InventoryStatus.checked_at)
                .where(and_(
                    InventoryStatus.plan_code == plan_code,
                    InventoryStatus.datacenter == datacenter,
                    InventoryStatus.subsidiary == subsidiary
                ))
                .order_by(InventoryStatus.checked_at.desc())
                .limit(1)
            )
            row = result.first()
            return dict(row._mapping) if row else None

    # ============ Out of Stock Tracking ============

    async def track_out_of_stock(self, plan_code: str, datacenter: str, subsidiary: str = 'US'):
        """Start tracking when an item goes out of stock."""
        async with self._session() as session:
            # Check if already tracking
            existing = await session.execute(
                select(OutOfStockTracking.id)
                .where(and_(
                    OutOfStockTracking.plan_code == plan_code,
                    OutOfStockTracking.datacenter == datacenter,
                    OutOfStockTracking.subsidiary == subsidiary,
                    OutOfStockTracking.returned_to_stock_at.is_(None)
                ))
            )
            
            if not existing.scalar_one_or_none():
                tracking = OutOfStockTracking(
                    plan_code=plan_code,
                    subsidiary=subsidiary,
                    datacenter=datacenter,
                    out_of_stock_since=func.now()
                )
                session.add(tracking)
                await session.commit()

    async def get_out_of_stock_duration(self, plan_code: str, datacenter: str, subsidiary: str = 'US') -> Optional[int]:
        """Get how long an item has been out of stock in minutes."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    (func.extract('epoch', func.now() - OutOfStockTracking.out_of_stock_since) / 60)
                    .label('minutes')
                )
                .where(and_(
                    OutOfStockTracking.plan_code == plan_code,
                    OutOfStockTracking.datacenter == datacenter,
                    OutOfStockTracking.subsidiary == subsidiary,
                    OutOfStockTracking.returned_to_stock_at.is_(None)
                ))
            )
            row = result.first()
            return int(row.minutes) if row and row.minutes else None

    async def mark_returned_to_stock(self, plan_code: str, datacenter: str, subsidiary: str = 'US') -> Optional[int]:
        """Mark item as returned to stock and return how long it was out."""
        async with self._session() as session:
            # First get the duration
            duration_result = await session.execute(
                select(
                    (func.extract('epoch', func.now() - OutOfStockTracking.out_of_stock_since) / 60)
                    .label('minutes')
                )
                .where(and_(
                    OutOfStockTracking.plan_code == plan_code,
                    OutOfStockTracking.datacenter == datacenter,
                    OutOfStockTracking.subsidiary == subsidiary,
                    OutOfStockTracking.returned_to_stock_at.is_(None)
                ))
            )
            duration_row = duration_result.first()
            minutes = int(duration_row.minutes) if duration_row and duration_row.minutes else None
            
            # Then update
            await session.execute(
                update(OutOfStockTracking)
                .where(and_(
                    OutOfStockTracking.plan_code == plan_code,
                    OutOfStockTracking.datacenter == datacenter,
                    OutOfStockTracking.subsidiary == subsidiary,
                    OutOfStockTracking.returned_to_stock_at.is_(None)
                ))
                .values(returned_to_stock_at=func.now())
            )
            await session.commit()
            
            return minutes

    async def get_in_stock_duration(self, plan_code: str, datacenter: str, subsidiary: str = 'US') -> Optional[int]:
        """Get how long an item has been in stock (since last return) in minutes."""
        async with self._session() as session:
            # Find the most recent returned_to_stock_at timestamp
            result = await session.execute(
                select(
                    (func.extract('epoch', func.now() - OutOfStockTracking.returned_to_stock_at) / 60)
                    .label('minutes')
                )
                .where(and_(
                    OutOfStockTracking.plan_code == plan_code,
                    OutOfStockTracking.datacenter == datacenter,
                    OutOfStockTracking.subsidiary == subsidiary,
                    OutOfStockTracking.returned_to_stock_at.isnot(None)
                ))
                .order_by(OutOfStockTracking.returned_to_stock_at.desc())
                .limit(1)
            )
            row = result.first()
            return int(row.minutes) if row and row.minutes else None

    # ============ Notifications ============

    async def save_notification(
        self,
        plan_code: str,
        datacenter: str,
        message: str,
        success: bool,
        error_message: Optional[str] = None,
        subsidiary: str = 'US'
    ):
        """Save notification history."""
        async with self._session() as session:
            notif = NotificationHistory(
                plan_code=plan_code,
                subsidiary=subsidiary,
                datacenter=datacenter,
                message=message,
                success=success,
                error_message=error_message
            )
            session.add(notif)
            await session.commit()

    # ============ Multi-tenant User Notifications ============

    async def get_users_subscribed_to_plan(self, plan_code: str, subsidiary: str = 'US') -> List[Dict[str, Any]]:
        """Get all users subscribed to a specific plan with their active webhooks."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    User.id.label('user_id'),
                    User.email,
                    UserWebhook.id.label('webhook_id'),
                    UserWebhook.webhook_url,
                    UserWebhook.webhook_name
                )
                .distinct()
                .join(UserPlanSubscription, UserPlanSubscription.user_id == User.id)
                .join(UserWebhook, and_(
                    UserWebhook.user_id == User.id,
                    UserWebhook.is_active == True
                ))
                .where(and_(
                    UserPlanSubscription.plan_code == plan_code,
                    or_(
                        UserPlanSubscription.subsidiary.is_(None),
                        UserPlanSubscription.subsidiary == subsidiary
                    ),
                    UserPlanSubscription.notify_on_available == True,
                    User.is_active == True
                ))
            )
            return [dict(row._mapping) for row in result.all()]

    async def save_user_notification(
        self,
        plan_code: str,
        datacenter: str,
        message: str,
        success: bool,
        error_message: Optional[str] = None,
        user_id: Optional[int] = None,
        webhook_id: Optional[int] = None,
        is_default_webhook: bool = False
    ):
        """Save user notification history."""
        async with self._session() as session:
            notif = UserNotificationHistory(
                user_id=user_id,
                webhook_id=webhook_id,
                plan_code=plan_code,
                datacenter=datacenter,
                message=message,
                success=success,
                error_message=error_message,
                is_default_webhook=is_default_webhook
            )
            session.add(notif)
            await session.commit()
