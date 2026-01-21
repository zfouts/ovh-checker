"""
SQLAlchemy-based Database Layer for OVH Checker API

This module provides an async database interface using SQLAlchemy 2.0 ORM.
"""

import os
import sys
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, update, delete, func, and_, or_, text, distinct
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

# Add parent directory to path to import shared models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from shared.models import (
    Base, Config, User, RefreshToken, ApiKey, Group, UserGroup,
    UserWebhook, GroupWebhook, UserPlanSubscription, GroupPlanSubscription,
    DatacenterLocation, MonitoredPlan, PlanPricing,
    InventoryStatus, OutOfStockTracking, NotificationHistory, UserNotificationHistory
)


# Currency symbols for formatting
CURRENCY_SYMBOLS = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CAD': 'CA$', 'AUD': 'A$'}


def format_price(price_microcents: int, currency: str = 'USD') -> str:
    """Convert microcents to formatted price string."""
    dollars = price_microcents / 100_000_000
    symbol = CURRENCY_SYMBOLS.get(currency, currency + ' ')
    return f"{symbol}{dollars:.2f}/mo"


def format_specs(vcpu: int, ram_gb: int, storage_gb: int, storage_type: str = 'SSD') -> str:
    """Format specs into a readable string."""
    return f"{vcpu} vCPU • {ram_gb} GB RAM • {storage_gb} GB {storage_type}"


class Database:
    """
    SQLAlchemy-based async database interface.
    
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

    # ============ User Management ============

    async def create_user(
        self, 
        email: str, 
        username: str, 
        password_hash: str,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Create a new user."""
        async with self._session() as session:
            try:
                user = User(
                    email=email.lower(),
                    username=username,
                    password_hash=password_hash,
                    is_admin=is_admin
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'is_admin': user.is_admin,
                    'is_active': user.is_active,
                    'created_at': user.created_at
                }
            except IntegrityError:
                await session.rollback()
                return None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        async with self._session() as session:
            result = await session.execute(
                select(User).where(User.email == email.lower())
            )
            user = result.scalar_one_or_none()
            if user:
                return {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'password_hash': user.password_hash,
                    'is_admin': user.is_admin,
                    'is_active': user.is_active,
                    'created_at': user.created_at,
                    'updated_at': user.updated_at,
                    'last_login_at': user.last_login_at
                }
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        async with self._session() as session:
            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                return {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'is_admin': user.is_admin,
                    'is_active': user.is_active,
                    'created_at': user.created_at,
                    'updated_at': user.updated_at,
                    'last_login_at': user.last_login_at
                }
            return None

    async def update_user_login(self, user_id: int):
        """Update user's last login timestamp."""
        async with self._session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_login_at=func.now())
            )
            await session.commit()

    async def update_user_profile(self, user_id: int, username: Optional[str] = None) -> bool:
        """Update user profile."""
        if not username:
            return True
        async with self._session() as session:
            try:
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(username=username, updated_at=func.now())
                )
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    async def update_user_password(self, user_id: int, password_hash: str):
        """Update user password."""
        async with self._session() as session:
            await session.execute(
                update(User)
                .where(User.id == user_id)
                .values(password_hash=password_hash, updated_at=func.now())
            )
            await session.commit()

    async def check_email_exists(self, email: str) -> bool:
        """Check if email already exists."""
        async with self._session() as session:
            result = await session.execute(
                select(User.id).where(User.email == email.lower()).limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def check_username_exists(self, username: str) -> bool:
        """Check if username already exists."""
        async with self._session() as session:
            result = await session.execute(
                select(User.id).where(User.username == username).limit(1)
            )
            return result.scalar_one_or_none() is not None

    # ============ Refresh Tokens ============

    async def save_refresh_token(self, user_id: int, token_hash: str, expires_at: datetime):
        """Save a refresh token."""
        async with self._session() as session:
            token = RefreshToken(
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at
            )
            session.add(token)
            await session.commit()

    async def get_refresh_token(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Get refresh token info."""
        async with self._session() as session:
            result = await session.execute(
                select(RefreshToken, User)
                .join(User, User.id == RefreshToken.user_id)
                .where(RefreshToken.token_hash == token_hash)
            )
            row = result.first()
            if row:
                token, user = row
                return {
                    'id': token.id,
                    'user_id': token.user_id,
                    'expires_at': token.expires_at,
                    'revoked_at': token.revoked_at,
                    'email': user.email,
                    'is_admin': user.is_admin,
                    'is_active': user.is_active
                }
            return None

    async def revoke_refresh_token(self, token_hash: str):
        """Revoke a refresh token."""
        async with self._session() as session:
            await session.execute(
                update(RefreshToken)
                .where(RefreshToken.token_hash == token_hash)
                .values(revoked_at=func.now())
            )
            await session.commit()

    async def revoke_all_user_tokens(self, user_id: int):
        """Revoke all refresh tokens for a user."""
        async with self._session() as session:
            await session.execute(
                update(RefreshToken)
                .where(and_(
                    RefreshToken.user_id == user_id,
                    RefreshToken.revoked_at.is_(None)
                ))
                .values(revoked_at=func.now())
            )
            await session.commit()

    async def cleanup_expired_tokens(self):
        """Remove expired refresh tokens."""
        async with self._session() as session:
            await session.execute(
                delete(RefreshToken).where(RefreshToken.expires_at < func.now())
            )
            await session.commit()

    # ============ API Keys ============

    async def create_api_key(
        self, 
        user_id: int, 
        key_hash: str, 
        name: str,
        expires_at: Optional[datetime] = None
    ) -> int:
        """Create an API key."""
        async with self._session() as session:
            api_key = ApiKey(
                user_id=user_id,
                key_hash=key_hash,
                name=name,
                expires_at=expires_at
            )
            session.add(api_key)
            await session.commit()
            await session.refresh(api_key)
            return api_key.id

    async def get_user_api_keys(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all API keys for a user."""
        async with self._session() as session:
            result = await session.execute(
                select(ApiKey)
                .where(and_(
                    ApiKey.user_id == user_id,
                    ApiKey.revoked_at.is_(None)
                ))
                .order_by(ApiKey.created_at.desc())
            )
            return [
                {
                    'id': key.id,
                    'name': key.name,
                    'last_used_at': key.last_used_at,
                    'expires_at': key.expires_at,
                    'created_at': key.created_at
                }
                for key in result.scalars().all()
            ]

    async def get_user_by_api_key(self, key_hash: str) -> Optional[Dict[str, Any]]:
        """Get user by API key hash."""
        async with self._session() as session:
            result = await session.execute(
                select(User)
                .join(ApiKey, ApiKey.user_id == User.id)
                .where(and_(
                    ApiKey.key_hash == key_hash,
                    ApiKey.revoked_at.is_(None),
                    or_(
                        ApiKey.expires_at.is_(None),
                        ApiKey.expires_at > func.now()
                    )
                ))
            )
            user = result.scalar_one_or_none()
            if user:
                return {
                    'id': user.id,
                    'email': user.email,
                    'is_admin': user.is_admin,
                    'is_active': user.is_active
                }
            return None

    async def update_api_key_last_used(self, key_hash: str):
        """Update API key last used timestamp."""
        async with self._session() as session:
            await session.execute(
                update(ApiKey)
                .where(ApiKey.key_hash == key_hash)
                .values(last_used_at=func.now())
            )
            await session.commit()

    async def revoke_api_key(self, user_id: int, key_id: int) -> bool:
        """Revoke an API key."""
        async with self._session() as session:
            result = await session.execute(
                update(ApiKey)
                .where(and_(ApiKey.id == key_id, ApiKey.user_id == user_id))
                .values(revoked_at=func.now())
            )
            await session.commit()
            return result.rowcount == 1

    # ============ User Webhooks ============

    async def create_user_webhook(
        self, 
        user_id: int, 
        webhook_url: str, 
        webhook_name: str = "My Webhook",
        webhook_type: str = "discord",
        bot_username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        include_price: bool = True,
        include_specs: bool = True,
        mention_role_id: Optional[str] = None,
        embed_color: Optional[str] = None,
        slack_channel: Optional[str] = None
    ) -> int:
        """Create a user webhook with customization options (Discord or Slack)."""
        async with self._session() as session:
            webhook = UserWebhook(
                user_id=user_id,
                webhook_url=webhook_url,
                webhook_name=webhook_name,
                webhook_type=webhook_type,
                bot_username=bot_username,
                avatar_url=avatar_url,
                include_price=include_price,
                include_specs=include_specs,
                mention_role_id=mention_role_id,
                embed_color=embed_color,
                slack_channel=slack_channel
            )
            session.add(webhook)
            await session.commit()
            await session.refresh(webhook)
            return webhook.id

    async def get_user_webhooks(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all webhooks for a user."""
        async with self._session() as session:
            result = await session.execute(
                select(UserWebhook)
                .where(UserWebhook.user_id == user_id)
                .order_by(UserWebhook.created_at.desc())
            )
            return [
                {
                    'id': wh.id,
                    'user_id': wh.user_id,
                    'webhook_url': wh.webhook_url,
                    'webhook_name': wh.webhook_name,
                    'webhook_type': wh.webhook_type,
                    'bot_username': wh.bot_username,
                    'avatar_url': wh.avatar_url,
                    'include_price': wh.include_price,
                    'include_specs': wh.include_specs,
                    'mention_role_id': wh.mention_role_id,
                    'embed_color': wh.embed_color,
                    'slack_channel': wh.slack_channel,
                    'is_active': wh.is_active,
                    'created_at': wh.created_at,
                    'updated_at': wh.updated_at
                }
                for wh in result.scalars().all()
            ]

    async def get_user_webhook(self, user_id: int, webhook_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific webhook for a user."""
        async with self._session() as session:
            result = await session.execute(
                select(UserWebhook)
                .where(and_(UserWebhook.id == webhook_id, UserWebhook.user_id == user_id))
            )
            wh = result.scalar_one_or_none()
            if wh:
                return {
                    'id': wh.id,
                    'user_id': wh.user_id,
                    'webhook_url': wh.webhook_url,
                    'webhook_name': wh.webhook_name,
                    'webhook_type': wh.webhook_type,
                    'bot_username': wh.bot_username,
                    'avatar_url': wh.avatar_url,
                    'include_price': wh.include_price,
                    'include_specs': wh.include_specs,
                    'mention_role_id': wh.mention_role_id,
                    'embed_color': wh.embed_color,
                    'slack_channel': wh.slack_channel,
                    'is_active': wh.is_active,
                    'created_at': wh.created_at,
                    'updated_at': wh.updated_at
                }
            return None

    async def update_user_webhook(
        self, 
        user_id: int, 
        webhook_id: int, 
        webhook_name: Optional[str] = None,
        bot_username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        include_price: Optional[bool] = None,
        include_specs: Optional[bool] = None,
        mention_role_id: Optional[str] = None,
        embed_color: Optional[str] = None,
        slack_channel: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> bool:
        """Update a user webhook."""
        updates = {'updated_at': func.now()}
        
        if webhook_name is not None:
            updates['webhook_name'] = webhook_name
        if bot_username is not None:
            updates['bot_username'] = bot_username
        if avatar_url is not None:
            updates['avatar_url'] = avatar_url
        if include_price is not None:
            updates['include_price'] = include_price
        if include_specs is not None:
            updates['include_specs'] = include_specs
        if mention_role_id is not None:
            updates['mention_role_id'] = mention_role_id
        if embed_color is not None:
            updates['embed_color'] = embed_color
        if slack_channel is not None:
            updates['slack_channel'] = slack_channel
        if is_active is not None:
            updates['is_active'] = is_active
        
        if len(updates) == 1:  # Only updated_at
            return True
        
        async with self._session() as session:
            result = await session.execute(
                update(UserWebhook)
                .where(and_(UserWebhook.id == webhook_id, UserWebhook.user_id == user_id))
                .values(**updates)
            )
            await session.commit()
            return result.rowcount == 1

    async def delete_user_webhook(self, user_id: int, webhook_id: int) -> bool:
        """Delete a user webhook."""
        async with self._session() as session:
            result = await session.execute(
                delete(UserWebhook)
                .where(and_(UserWebhook.id == webhook_id, UserWebhook.user_id == user_id))
            )
            await session.commit()
            return result.rowcount == 1

    # ============ User Plan Subscriptions ============

    async def get_user_subscriptions(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all plan subscriptions for a user with plan details."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    UserPlanSubscription,
                    MonitoredPlan.display_name,
                    MonitoredPlan.vcpu,
                    MonitoredPlan.ram_gb,
                    MonitoredPlan.storage_gb,
                    MonitoredPlan.storage_type,
                    PlanPricing.price_microcents,
                    PlanPricing.currency
                )
                .join(MonitoredPlan, and_(
                    MonitoredPlan.plan_code == UserPlanSubscription.plan_code,
                    MonitoredPlan.subsidiary == UserPlanSubscription.subsidiary
                ))
                .outerjoin(PlanPricing, and_(
                    PlanPricing.plan_code == UserPlanSubscription.plan_code,
                    PlanPricing.subsidiary == UserPlanSubscription.subsidiary,
                    PlanPricing.commitment_months == 0
                ))
                .where(UserPlanSubscription.user_id == user_id)
                .order_by(UserPlanSubscription.subsidiary, MonitoredPlan.plan_code)
            )
            
            results = []
            for row in result.all():
                sub = row[0]
                r = {
                    'id': sub.id,
                    'user_id': sub.user_id,
                    'plan_code': sub.plan_code,
                    'subsidiary': sub.subsidiary,
                    'notify_on_available': sub.notify_on_available,
                    'created_at': sub.created_at,
                    'display_name': row.display_name,
                    'vcpu': row.vcpu,
                    'ram_gb': row.ram_gb,
                    'storage_gb': row.storage_gb,
                    'storage_type': row.storage_type,
                    'price_microcents': row.price_microcents,
                    'currency': row.currency
                }
                
                if r.get('price_microcents'):
                    r['price'] = format_price(r['price_microcents'], r.get('currency', 'USD'))
                else:
                    r['price'] = None
                
                if r.get('vcpu') and r.get('ram_gb'):
                    r['specs'] = format_specs(r['vcpu'], r['ram_gb'], r['storage_gb'], r.get('storage_type', 'SSD'))
                else:
                    r['specs'] = None
                
                results.append(r)
            return results

    async def add_user_subscription(
        self, 
        user_id: int, 
        plan_code: str,
        subsidiary: str = 'US',
        notify_on_available: bool = True
    ) -> Optional[int]:
        """Add a plan subscription for a user for a specific subsidiary."""
        async with self._session() as session:
            try:
                # Use PostgreSQL upsert
                stmt = pg_insert(UserPlanSubscription).values(
                    user_id=user_id,
                    plan_code=plan_code,
                    subsidiary=subsidiary,
                    notify_on_available=notify_on_available
                ).on_conflict_do_update(
                    index_elements=['user_id', 'plan_code', 'subsidiary'],
                    set_={'notify_on_available': notify_on_available}
                ).returning(UserPlanSubscription.id)
                
                result = await session.execute(stmt)
                await session.commit()
                row = result.first()
                return row[0] if row else None
            except IntegrityError:
                await session.rollback()
                return None

    async def update_user_subscription(
        self, 
        user_id: int, 
        plan_code: str,
        subsidiary: str,
        notify_on_available: bool
    ) -> bool:
        """Update a user's subscription for a plan in a specific subsidiary."""
        async with self._session() as session:
            result = await session.execute(
                update(UserPlanSubscription)
                .where(and_(
                    UserPlanSubscription.user_id == user_id,
                    UserPlanSubscription.plan_code == plan_code,
                    UserPlanSubscription.subsidiary == subsidiary
                ))
                .values(notify_on_available=notify_on_available)
            )
            await session.commit()
            return result.rowcount == 1

    async def remove_user_subscription(self, user_id: int, plan_code: str, subsidiary: str = None) -> bool:
        """Remove a plan subscription for a user. If subsidiary is None, removes all subsidiaries."""
        async with self._session() as session:
            if subsidiary:
                stmt = delete(UserPlanSubscription).where(and_(
                    UserPlanSubscription.user_id == user_id,
                    UserPlanSubscription.plan_code == plan_code,
                    UserPlanSubscription.subsidiary == subsidiary
                ))
            else:
                stmt = delete(UserPlanSubscription).where(and_(
                    UserPlanSubscription.user_id == user_id,
                    UserPlanSubscription.plan_code == plan_code
                ))
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def bulk_update_subscriptions(
        self, 
        user_id: int, 
        plan_codes: List[str],
        subsidiary: str = 'US',
        notify_on_available: bool = True
    ) -> int:
        """Bulk add/update subscriptions for multiple plans in a specific subsidiary."""
        async with self._session() as session:
            count = 0
            for plan_code in plan_codes:
                try:
                    stmt = pg_insert(UserPlanSubscription).values(
                        user_id=user_id,
                        plan_code=plan_code,
                        subsidiary=subsidiary,
                        notify_on_available=notify_on_available
                    ).on_conflict_do_update(
                        index_elements=['user_id', 'plan_code', 'subsidiary'],
                        set_={'notify_on_available': notify_on_available}
                    )
                    await session.execute(stmt)
                    count += 1
                except IntegrityError:
                    pass
            await session.commit()
            return count

    async def get_users_subscribed_to_plan(self, plan_code: str) -> List[Dict[str, Any]]:
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
                    UserPlanSubscription.notify_on_available == True,
                    User.is_active == True
                ))
            )
            return [dict(row._mapping) for row in result.all()]

    # ============ User Notification History ============

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

    async def get_user_notification_history(self, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get notification history for a user."""
        async with self._session() as session:
            result = await session.execute(
                select(UserNotificationHistory)
                .where(UserNotificationHistory.user_id == user_id)
                .order_by(UserNotificationHistory.sent_at.desc())
                .limit(limit)
            )
            return [
                {
                    'id': n.id,
                    'user_id': n.user_id,
                    'webhook_id': n.webhook_id,
                    'plan_code': n.plan_code,
                    'datacenter': n.datacenter,
                    'message': n.message,
                    'sent_at': n.sent_at,
                    'success': n.success,
                    'error_message': n.error_message,
                    'is_default_webhook': n.is_default_webhook
                }
                for n in result.scalars().all()
            ]

    # ============ Config ============

    async def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value."""
        async with self._session() as session:
            result = await session.execute(
                select(Config.value).where(Config.key == key)
            )
            row = result.scalar_one_or_none()
            return row

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

    async def get_all_config(self) -> Dict[str, str]:
        """Get all configuration values."""
        async with self._session() as session:
            result = await session.execute(select(Config))
            return {c.key: c.value for c in result.scalars().all()}

    async def get_active_subsidiaries(self) -> List[str]:
        """Get list of monitored subsidiaries from config."""
        config = await self.get_all_config()
        subsidiaries_str = config.get('monitored_subsidiaries', 'US')
        if subsidiaries_str.upper() == 'ALL':
            return ['US', 'CA', 'FR', 'DE', 'GB', 'ES', 'IT', 'NL', 'PL', 'PT', 'IE', 'AU', 'SG', 'ASIA', 'IN', 'WE', 'WS']
        return [s.strip().upper() for s in subsidiaries_str.split(',') if s.strip()]

    async def get_subsidiaries_with_data(self) -> List[str]:
        """Get list of subsidiaries that have inventory data."""
        async with self._session() as session:
            result = await session.execute(
                select(distinct(InventoryStatus.subsidiary))
                .order_by(InventoryStatus.subsidiary)
            )
            return [row[0] for row in result.all()]

    async def get_monitored_plans(self, subsidiary: str = None) -> List[Dict[str, Any]]:
        """Get all monitored plans with pricing and specs."""
        async with self._session() as session:
            query = (
                select(
                    MonitoredPlan,
                    PlanPricing.price_microcents,
                    PlanPricing.currency,
                    PlanPricing.commitment_months.label('pricing_commitment')
                )
                .outerjoin(PlanPricing, and_(
                    PlanPricing.plan_code == MonitoredPlan.plan_code,
                    PlanPricing.subsidiary == MonitoredPlan.subsidiary,
                    PlanPricing.commitment_months == 0
                ))
            )
            
            if subsidiary:
                query = query.where(MonitoredPlan.subsidiary == subsidiary)
                query = query.order_by(MonitoredPlan.is_orderable.desc(), MonitoredPlan.plan_code)
            else:
                query = query.order_by(
                    MonitoredPlan.subsidiary, 
                    MonitoredPlan.is_orderable.desc(), 
                    MonitoredPlan.plan_code
                )
            
            result = await session.execute(query)
            
            results = []
            for row in result.all():
                mp = row[0]
                r = {
                    'id': mp.id,
                    'plan_code': mp.plan_code,
                    'subsidiary': mp.subsidiary,
                    'display_name': mp.display_name,
                    'url': mp.url,
                    'purchase_url': mp.purchase_url,
                    'enabled': mp.enabled,
                    'created_at': mp.created_at,
                    'vcpu': mp.vcpu,
                    'ram_gb': mp.ram_gb,
                    'storage_gb': mp.storage_gb,
                    'storage_type': mp.storage_type,
                    'bandwidth_mbps': mp.bandwidth_mbps,
                    'description': mp.description,
                    'catalog_status': mp.catalog_status,
                    'first_seen_at': mp.first_seen_at,
                    'last_seen_at': mp.last_seen_at,
                    'discontinued_at': mp.discontinued_at,
                    'is_orderable': mp.is_orderable,
                    'visibility_tags': mp.visibility_tags,
                    'product_line': mp.product_line,
                    'price_microcents': row.price_microcents,
                    'currency': row.currency,
                    'pricing_commitment': row.pricing_commitment
                }
                
                if r.get('price_microcents'):
                    r['price'] = format_price(r['price_microcents'], r.get('currency', 'USD'))
                else:
                    r['price'] = None
                
                if r.get('vcpu') and r.get('ram_gb'):
                    r['specs'] = format_specs(r['vcpu'], r['ram_gb'], r['storage_gb'], r.get('storage_type', 'SSD'))
                else:
                    r['specs'] = None
                
                results.append(r)
            return results

    async def add_monitored_plan(self, plan_code: str, display_name: str, url: str, subsidiary: str = 'US') -> int:
        """Add a new monitored plan for a specific subsidiary."""
        async with self._session() as session:
            plan = MonitoredPlan(
                plan_code=plan_code,
                subsidiary=subsidiary,
                display_name=display_name,
                url=url
            )
            session.add(plan)
            await session.commit()
            await session.refresh(plan)
            return plan.id

    async def update_monitored_plan(self, plan_code: str, enabled: bool, subsidiary: str = None):
        """Enable or disable a monitored plan."""
        async with self._session() as session:
            if subsidiary:
                stmt = (
                    update(MonitoredPlan)
                    .where(and_(
                        MonitoredPlan.plan_code == plan_code,
                        MonitoredPlan.subsidiary == subsidiary
                    ))
                    .values(enabled=enabled)
                )
            else:
                stmt = (
                    update(MonitoredPlan)
                    .where(MonitoredPlan.plan_code == plan_code)
                    .values(enabled=enabled)
                )
            await session.execute(stmt)
            await session.commit()

    async def delete_monitored_plan(self, plan_code: str, subsidiary: str = None):
        """Delete a monitored plan."""
        async with self._session() as session:
            if subsidiary:
                stmt = delete(MonitoredPlan).where(and_(
                    MonitoredPlan.plan_code == plan_code,
                    MonitoredPlan.subsidiary == subsidiary
                ))
            else:
                stmt = delete(MonitoredPlan).where(MonitoredPlan.plan_code == plan_code)
            await session.execute(stmt)
            await session.commit()

    async def get_current_status(self, subsidiary: str = None) -> List[Dict[str, Any]]:
        """Get the latest status for each plan/datacenter combination, grouped by plan."""
        async with self._session() as session:
            # Use raw SQL for the complex CTE query - SQLAlchemy can handle it but this is clearer
            base_query = """
                WITH latest AS (
                    SELECT DISTINCT ON (plan_code, subsidiary, datacenter) 
                        id, plan_code, subsidiary, datacenter, datacenter_code, is_available, 
                        linux_status, checked_at
                    FROM inventory_status
                    {where_clause}
                    ORDER BY plan_code, subsidiary, datacenter, checked_at DESC
                )
                SELECT 
                    l.*,
                    mp.display_name,
                    mp.purchase_url,
                    mp.vcpu,
                    mp.ram_gb,
                    mp.storage_gb,
                    mp.storage_type,
                    mp.bandwidth_mbps,
                    mp.description as plan_description,
                    mp.is_orderable,
                    mp.product_line,
                    pp.price_microcents,
                    pp.currency,
                    pp.commitment_months as pricing_commitment,
                    dl.display_name as location_display_name,
                    dl.city as location_city,
                    dl.country as location_country,
                    dl.country_code as location_country_code,
                    dl.flag as location_flag,
                    dl.region as location_region,
                    COALESCE(
                        (SELECT EXTRACT(EPOCH FROM (NOW() - out_of_stock_since)) / 60
                         FROM out_of_stock_tracking 
                         WHERE plan_code = l.plan_code AND subsidiary = l.subsidiary 
                         AND datacenter = l.datacenter AND returned_to_stock_at IS NULL
                         ORDER BY out_of_stock_since DESC LIMIT 1),
                        0
                    ) as out_of_stock_minutes
                FROM latest l
                LEFT JOIN monitored_plans mp ON mp.plan_code = l.plan_code AND mp.subsidiary = l.subsidiary
                LEFT JOIN plan_pricing pp ON pp.plan_code = l.plan_code AND pp.subsidiary = l.subsidiary AND pp.commitment_months = 0
                LEFT JOIN datacenter_locations dl ON dl.datacenter_code = l.datacenter_code AND dl.subsidiary = l.subsidiary
                {order_clause}
            """
            
            if subsidiary:
                query = base_query.format(
                    where_clause="WHERE subsidiary = :subsidiary",
                    order_clause="ORDER BY mp.is_orderable DESC, l.plan_code, l.datacenter"
                )
                result = await session.execute(text(query), {'subsidiary': subsidiary})
            else:
                query = base_query.format(
                    where_clause="",
                    order_clause="ORDER BY l.subsidiary, mp.is_orderable DESC, l.plan_code, l.datacenter"
                )
                result = await session.execute(text(query))
            
            results = []
            for row in result.mappings().all():
                r = dict(row)
                if r.get('price_microcents'):
                    r['price'] = format_price(r['price_microcents'], r.get('currency', 'USD'))
                else:
                    r['price'] = None
                
                if r.get('vcpu') and r.get('ram_gb'):
                    r['specs'] = format_specs(r['vcpu'], r['ram_gb'], r['storage_gb'], r.get('storage_type', 'SSD'))
                else:
                    r['specs'] = None
                
                results.append(r)
            return results

    async def get_plan_pricing(self, plan_code: str, subsidiary: str = None) -> List[Dict[str, Any]]:
        """Get all pricing tiers for a plan across all or specific subsidiaries."""
        async with self._session() as session:
            query = select(PlanPricing).where(PlanPricing.plan_code == plan_code)
            
            if subsidiary:
                query = query.where(PlanPricing.subsidiary == subsidiary)
                query = query.order_by(PlanPricing.commitment_months)
            else:
                query = query.order_by(PlanPricing.subsidiary, PlanPricing.commitment_months)
            
            result = await session.execute(query)
            
            results = []
            for pp in result.scalars().all():
                r = {
                    'subsidiary': pp.subsidiary,
                    'commitment_months': pp.commitment_months,
                    'price_microcents': pp.price_microcents,
                    'currency': pp.currency,
                    'description': pp.description,
                    'updated_at': pp.updated_at
                }
                if r.get('price_microcents'):
                    r['price'] = format_price(r['price_microcents'], r.get('currency', 'USD'))
                results.append(r)
            return results

    async def get_pricing_last_updated(self) -> Optional[str]:
        """Get the timestamp of the last pricing update."""
        return await self.get_config("pricing_last_updated")

    async def get_status_history(self, plan_code: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get status history, optionally filtered by plan code."""
        async with self._session() as session:
            query = select(
                InventoryStatus.plan_code,
                InventoryStatus.datacenter,
                InventoryStatus.is_available,
                InventoryStatus.checked_at
            ).order_by(InventoryStatus.checked_at.desc()).limit(limit)
            
            if plan_code:
                query = query.where(InventoryStatus.plan_code == plan_code)
            
            result = await session.execute(query)
            return [dict(row._mapping) for row in result.all()]

    async def get_notification_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get notification history."""
        async with self._session() as session:
            result = await session.execute(
                select(NotificationHistory)
                .order_by(NotificationHistory.sent_at.desc())
                .limit(limit)
            )
            return [
                {
                    'plan_code': n.plan_code,
                    'datacenter': n.datacenter,
                    'message': n.message,
                    'sent_at': n.sent_at,
                    'success': n.success,
                    'error_message': n.error_message
                }
                for n in result.scalars().all()
            ]

    async def save_notification(
        self,
        plan_code: str,
        datacenter: str,
        message: str,
        success: bool,
        error_message: Optional[str] = None
    ):
        """Save notification history."""
        async with self._session() as session:
            notif = NotificationHistory(
                plan_code=plan_code,
                datacenter=datacenter,
                message=message,
                success=success,
                error_message=error_message
            )
            session.add(notif)
            await session.commit()

    async def get_datacenter_locations(self, subsidiary: str = None) -> Dict[str, Dict[str, Any]]:
        """Get all datacenter locations as a mapping from datacenter_code to info."""
        async with self._session() as session:
            query = select(DatacenterLocation).order_by(
                DatacenterLocation.subsidiary, DatacenterLocation.datacenter_code
            )
            
            if subsidiary:
                query = query.where(DatacenterLocation.subsidiary == subsidiary)
            
            result = await session.execute(query)
            
            if subsidiary:
                return {
                    dl.datacenter_code: {
                        'subsidiary': dl.subsidiary,
                        'display_name': dl.display_name,
                        'city': dl.city,
                        'country': dl.country,
                        'country_code': dl.country_code,
                        'flag': dl.flag,
                        'region': dl.region
                    }
                    for dl in result.scalars().all()
                }
            else:
                return {
                    f"{dl.subsidiary}:{dl.datacenter_code}": {
                        'subsidiary': dl.subsidiary,
                        'datacenter_code': dl.datacenter_code,
                        'display_name': dl.display_name,
                        'city': dl.city,
                        'country': dl.country,
                        'country_code': dl.country_code,
                        'flag': dl.flag,
                        'region': dl.region
                    }
                    for dl in result.scalars().all()
                }

    # ============ Admin User Management ============

    async def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users (admin only)."""
        async with self._session() as session:
            result = await session.execute(
                select(User).order_by(User.created_at.desc())
            )
            return [
                {
                    'id': u.id,
                    'email': u.email,
                    'username': u.username,
                    'is_active': u.is_active,
                    'is_admin': u.is_admin,
                    'created_at': u.created_at,
                    'last_login': u.last_login_at
                }
                for u in result.scalars().all()
            ]

    async def admin_update_user(
        self, 
        user_id: int, 
        is_active: Optional[bool] = None,
        is_admin: Optional[bool] = None
    ) -> bool:
        """Update user status (admin only)."""
        updates = {}
        if is_active is not None:
            updates['is_active'] = is_active
        if is_admin is not None:
            updates['is_admin'] = is_admin
        
        if not updates:
            return False
        
        async with self._session() as session:
            result = await session.execute(
                update(User).where(User.id == user_id).values(**updates)
            )
            await session.commit()
            return result.rowcount == 1

    async def admin_delete_user(self, user_id: int) -> bool:
        """Delete a user (admin only)."""
        async with self._session() as session:
            result = await session.execute(
                delete(User).where(User.id == user_id)
            )
            await session.commit()
            return result.rowcount == 1

    async def admin_get_user_details(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed user info including webhooks and subscriptions (admin only)."""
        async with self._session() as session:
            user_result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = user_result.scalar_one_or_none()
            if not user:
                return None
            
            result = {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'is_active': user.is_active,
                'is_admin': user.is_admin,
                'created_at': user.created_at,
                'last_login': user.last_login_at
            }
            
            # Get webhook count
            webhook_result = await session.execute(
                select(func.count()).select_from(UserWebhook).where(UserWebhook.user_id == user_id)
            )
            result['webhook_count'] = webhook_result.scalar()
            
            # Get subscription count
            sub_result = await session.execute(
                select(func.count()).select_from(UserPlanSubscription).where(UserPlanSubscription.user_id == user_id)
            )
            result['subscription_count'] = sub_result.scalar()
            
            return result

    async def admin_create_user(
        self,
        email: str,
        username: str,
        password_hash: str,
        is_active: bool = True,
        is_admin: bool = False
    ) -> Optional[Dict[str, Any]]:
        """Create a user (admin only)."""
        async with self._session() as session:
            try:
                user = User(
                    email=email,
                    username=username,
                    password_hash=password_hash,
                    is_admin=is_admin,
                    is_active=is_active
                )
                session.add(user)
                await session.commit()
                await session.refresh(user)
                return {
                    'id': user.id,
                    'email': user.email,
                    'username': user.username,
                    'is_active': user.is_active,
                    'is_admin': user.is_admin,
                    'created_at': user.created_at
                }
            except IntegrityError:
                await session.rollback()
                return None

    # ============ Group Management ============

    async def create_group(
        self, 
        name: str, 
        description: Optional[str], 
        created_by: int
    ) -> Optional[Dict[str, Any]]:
        """Create a new group."""
        async with self._session() as session:
            try:
                group = Group(
                    name=name,
                    description=description,
                    created_by=created_by
                )
                session.add(group)
                await session.flush()
                
                # Add creator as owner
                membership = UserGroup(
                    user_id=created_by,
                    group_id=group.id,
                    role='owner'
                )
                session.add(membership)
                
                await session.commit()
                await session.refresh(group)
                
                return {
                    'id': group.id,
                    'name': group.name,
                    'description': group.description,
                    'created_by': group.created_by,
                    'created_at': group.created_at
                }
            except IntegrityError:
                await session.rollback()
                return None

    async def get_all_groups(self) -> List[Dict[str, Any]]:
        """Get all groups with member counts."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    Group,
                    func.count(UserGroup.user_id).label('member_count')
                )
                .outerjoin(UserGroup, Group.id == UserGroup.group_id)
                .group_by(Group.id)
                .order_by(Group.name)
            )
            return [
                {
                    'id': row[0].id,
                    'name': row[0].name,
                    'description': row[0].description,
                    'created_by': row[0].created_by,
                    'created_at': row[0].created_at,
                    'member_count': row.member_count
                }
                for row in result.all()
            ]

    async def get_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get a group by ID."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    Group,
                    func.count(UserGroup.user_id).label('member_count')
                )
                .outerjoin(UserGroup, Group.id == UserGroup.group_id)
                .where(Group.id == group_id)
                .group_by(Group.id)
            )
            row = result.first()
            if row:
                return {
                    'id': row[0].id,
                    'name': row[0].name,
                    'description': row[0].description,
                    'created_by': row[0].created_by,
                    'created_at': row[0].created_at,
                    'member_count': row.member_count
                }
            return None

    async def update_group(
        self, 
        group_id: int, 
        name: Optional[str] = None, 
        description: Optional[str] = None
    ) -> bool:
        """Update a group."""
        updates = {'updated_at': func.now()}
        if name is not None:
            updates['name'] = name
        if description is not None:
            updates['description'] = description
        
        if len(updates) == 1:  # Only updated_at
            return True
        
        async with self._session() as session:
            result = await session.execute(
                update(Group).where(Group.id == group_id).values(**updates)
            )
            await session.commit()
            return result.rowcount == 1

    async def delete_group(self, group_id: int) -> bool:
        """Delete a group."""
        async with self._session() as session:
            result = await session.execute(
                delete(Group).where(Group.id == group_id)
            )
            await session.commit()
            return result.rowcount == 1

    async def get_group_members(self, group_id: int) -> List[Dict[str, Any]]:
        """Get all members of a group."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    UserGroup.user_id,
                    User.username,
                    User.email,
                    UserGroup.role,
                    UserGroup.joined_at
                )
                .join(User, UserGroup.user_id == User.id)
                .where(UserGroup.group_id == group_id)
                .order_by(UserGroup.role, User.username)
            )
            return [dict(row._mapping) for row in result.all()]

    async def add_group_member(
        self, 
        group_id: int, 
        user_id: int, 
        role: str = "member"
    ) -> bool:
        """Add a user to a group."""
        async with self._session() as session:
            try:
                stmt = pg_insert(UserGroup).values(
                    user_id=user_id,
                    group_id=group_id,
                    role=role
                ).on_conflict_do_update(
                    index_elements=['user_id', 'group_id'],
                    set_={'role': role}
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    async def remove_group_member(self, group_id: int, user_id: int) -> bool:
        """Remove a user from a group."""
        async with self._session() as session:
            result = await session.execute(
                delete(UserGroup).where(and_(
                    UserGroup.group_id == group_id,
                    UserGroup.user_id == user_id
                ))
            )
            await session.commit()
            return result.rowcount == 1

    async def get_user_groups(self, user_id: int) -> List[Dict[str, Any]]:
        """Get all groups a user belongs to."""
        async with self._session() as session:
            result = await session.execute(
                select(
                    Group.id,
                    Group.name,
                    Group.description,
                    UserGroup.role,
                    UserGroup.joined_at
                )
                .join(UserGroup, Group.id == UserGroup.group_id)
                .where(UserGroup.user_id == user_id)
                .order_by(Group.name)
            )
            return [dict(row._mapping) for row in result.all()]
