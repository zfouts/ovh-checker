"""
SQLAlchemy ORM Models for OVH Checker

This module defines all database models using SQLAlchemy 2.0 declarative syntax
with async support.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import (
    String, Text, Boolean, Integer, BigInteger, DateTime, 
    ForeignKey, UniqueConstraint, Index, Numeric, JSON
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""
    pass


# =============================================================================
# CONFIGURATION
# =============================================================================

class Config(Base):
    """Configuration key-value store."""
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )


# =============================================================================
# USERS & AUTHENTICATION
# =============================================================================

class User(Base):
    """User accounts for multi-tenant authentication."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    webhooks: Mapped[List["UserWebhook"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    plan_subscriptions: Mapped[List["UserPlanSubscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    group_memberships: Mapped[List["UserGroup"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[List["ApiKey"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    created_groups: Mapped[List["Group"]] = relationship(back_populates="created_by_user")
    notification_history: Mapped[List["UserNotificationHistory"]] = relationship(back_populates="user")

    __table_args__ = (
        Index("idx_users_email", "email"),
        Index("idx_users_username", "username"),
    )


class RefreshToken(Base):
    """JWT refresh tokens for session management."""
    __tablename__ = "refresh_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="refresh_tokens")

    __table_args__ = (
        Index("idx_refresh_tokens_user_id", "user_id"),
        Index("idx_refresh_tokens_expires", "expires_at"),
    )


class ApiKey(Base):
    """API keys for programmatic access."""
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_user_id", "user_id"),
    )


# =============================================================================
# GROUPS
# =============================================================================

class Group(Base):
    """Groups for organizing users and shared alert configurations."""
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    created_by_user: Mapped[Optional["User"]] = relationship(back_populates="created_groups")
    members: Mapped[List["UserGroup"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    webhooks: Mapped[List["GroupWebhook"]] = relationship(back_populates="group", cascade="all, delete-orphan")
    plan_subscriptions: Mapped[List["GroupPlanSubscription"]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class UserGroup(Base):
    """User-Group membership (many-to-many)."""
    __tablename__ = "user_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="member")  # 'owner', 'admin', 'member'
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="group_memberships")
    group: Mapped["Group"] = relationship(back_populates="members")

    __table_args__ = (
        UniqueConstraint("user_id", "group_id"),
        Index("idx_user_groups_user_id", "user_id"),
        Index("idx_user_groups_group_id", "group_id"),
    )


# =============================================================================
# WEBHOOKS
# =============================================================================

class UserWebhook(Base):
    """User Discord webhooks with customization options."""
    __tablename__ = "user_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_name: Mapped[str] = mapped_column(String(255), default="My Discord")
    bot_username: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    include_price: Mapped[bool] = mapped_column(Boolean, default=True)
    include_specs: Mapped[bool] = mapped_column(Boolean, default=True)
    mention_role_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embed_color: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship(back_populates="webhooks")

    __table_args__ = (
        Index("idx_user_webhooks_user_id", "user_id"),
    )


class GroupWebhook(Base):
    """Group Discord webhooks (shared webhooks for a group)."""
    __tablename__ = "group_webhooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    webhook_url: Mapped[str] = mapped_column(Text, nullable=False)
    webhook_name: Mapped[str] = mapped_column(String(255), default="Group Discord")
    bot_username: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    include_price: Mapped[bool] = mapped_column(Boolean, default=True)
    include_specs: Mapped[bool] = mapped_column(Boolean, default=True)
    mention_role_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embed_color: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    group: Mapped["Group"] = relationship(back_populates="webhooks")

    __table_args__ = (
        Index("idx_group_webhooks_group_id", "group_id"),
    )


# =============================================================================
# PLAN SUBSCRIPTIONS
# =============================================================================

class UserPlanSubscription(Base):
    """User plan subscriptions (which plans each user wants notifications for)."""
    __tablename__ = "user_plan_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # NULL = all subsidiaries
    notify_on_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="plan_subscriptions")

    __table_args__ = (
        UniqueConstraint("user_id", "plan_code", "subsidiary"),
        Index("idx_user_plan_subs_user_id", "user_id"),
        Index("idx_user_plan_subs_plan_code", "plan_code"),
        Index("idx_user_plan_subs_subsidiary", "subsidiary"),
    )


class GroupPlanSubscription(Base):
    """Group plan subscriptions."""
    __tablename__ = "group_plan_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # NULL = all subsidiaries
    notify_on_available: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    group: Mapped["Group"] = relationship(back_populates="plan_subscriptions")

    __table_args__ = (
        UniqueConstraint("group_id", "plan_code", "subsidiary"),
        Index("idx_group_plan_subs_group_id", "group_id"),
        Index("idx_group_plan_subs_subsidiary", "subsidiary"),
    )


# =============================================================================
# DATACENTER & PLANS
# =============================================================================

class DatacenterLocation(Base):
    """Datacenter locations mapping with geographic info."""
    __tablename__ = "datacenter_locations"

    datacenter_code: Mapped[str] = mapped_column(String(100), primary_key=True)
    subsidiary: Mapped[str] = mapped_column(String(10), primary_key=True, default="US")
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    city: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    flag: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    region: Mapped[str] = mapped_column(String(50), nullable=False)  # US, EU, CA, APAC
    latitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Numeric(10, 7), nullable=True)

    __table_args__ = (
        Index("idx_datacenter_locations_subsidiary", "subsidiary"),
    )


class MonitoredPlan(Base):
    """VPS plans to monitor from OVH catalog."""
    __tablename__ = "monitored_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    purchase_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Lifecycle tracking
    catalog_status: Mapped[str] = mapped_column(String(50), default="active")  # 'active', 'discontinued', 'new'
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )
    discontinued_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Visibility/orderable status
    is_orderable: Mapped[bool] = mapped_column(Boolean, default=True)
    visibility_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    product_line: Mapped[str] = mapped_column(String(50), default="legacy")  # '2025', 'legacy'
    
    # Specs from catalog API
    vcpu: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ram_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_gb: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    storage_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bandwidth_mbps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationships
    pricing: Mapped[List["PlanPricing"]] = relationship(
        back_populates="plan",
        primaryjoin="and_(MonitoredPlan.plan_code==PlanPricing.plan_code, "
                    "MonitoredPlan.subsidiary==PlanPricing.subsidiary)",
        foreign_keys="[PlanPricing.plan_code, PlanPricing.subsidiary]",
        viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("plan_code", "subsidiary"),
    )


class PlanPricing(Base):
    """Plan pricing with different commitment periods."""
    __tablename__ = "plan_pricing"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    commitment_months: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_microcents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="USD")
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )

    # Relationship back to MonitoredPlan
    plan: Mapped[Optional["MonitoredPlan"]] = relationship(
        back_populates="pricing",
        primaryjoin="and_(PlanPricing.plan_code==MonitoredPlan.plan_code, "
                    "PlanPricing.subsidiary==MonitoredPlan.subsidiary)",
        foreign_keys="[PlanPricing.plan_code, PlanPricing.subsidiary]",
        viewonly=True
    )

    __table_args__ = (
        UniqueConstraint("plan_code", "subsidiary", "commitment_months"),
        Index("idx_plan_pricing_plan_code", "plan_code"),
        Index("idx_plan_pricing_subsidiary", "subsidiary"),
    )


# =============================================================================
# INVENTORY TRACKING
# =============================================================================

class InventoryStatus(Base):
    """Inventory status history for each plan/datacenter combo."""
    __tablename__ = "inventory_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    datacenter: Mapped[str] = mapped_column(String(100), nullable=False)
    datacenter_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    linux_status: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    raw_response: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_inventory_status_plan_code", "plan_code"),
        Index("idx_inventory_status_checked_at", "checked_at"),
        Index("idx_inventory_status_subsidiary", "subsidiary"),
    )


class OutOfStockTracking(Base):
    """Track when items go out of stock for notification timing."""
    __tablename__ = "out_of_stock_tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    datacenter: Mapped[str] = mapped_column(String(100), nullable=False)
    out_of_stock_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    returned_to_stock_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("plan_code", "subsidiary", "datacenter", "out_of_stock_since"),
        Index("idx_out_of_stock_tracking_plan_dc", "plan_code", "datacenter"),
        Index("idx_out_of_stock_tracking_subsidiary", "subsidiary"),
    )


# =============================================================================
# NOTIFICATION HISTORY
# =============================================================================

class NotificationHistory(Base):
    """System default webhook notification history."""
    __tablename__ = "notification_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    subsidiary: Mapped[str] = mapped_column(String(10), nullable=False, default="US")
    datacenter: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default_webhook: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (
        Index("idx_notification_history_subsidiary", "subsidiary"),
    )


class UserNotificationHistory(Base):
    """User-specific notification history."""
    __tablename__ = "user_notification_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    webhook_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("user_webhooks.id", ondelete="SET NULL"), nullable=True
    )
    plan_code: Mapped[str] = mapped_column(String(255), nullable=False)
    datacenter: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_default_webhook: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    user: Mapped[Optional["User"]] = relationship(back_populates="notification_history")

    __table_args__ = (
        Index("idx_user_notif_history_user_id", "user_id"),
        Index("idx_user_notif_history_sent_at", "sent_at"),
    )
