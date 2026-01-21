from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
import re


# Password complexity regex pattern
# Requires: 8+ chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char
PASSWORD_PATTERN = re.compile(
    r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[@$!%*?&^#()_+\-=\[\]{};:\'",.<>\\|`~])[A-Za-z\d@$!%*?&^#()_+\-=\[\]{};:\'",.<>\\|`~]{8,128}$'
)


def validate_password_complexity(password: str) -> str:
    """Validate password meets complexity requirements."""
    if len(password) < 8:
        raise ValueError('Password must be at least 8 characters')
    if len(password) > 128:
        raise ValueError('Password must not exceed 128 characters')
    if not re.search(r'[a-z]', password):
        raise ValueError('Password must contain at least one lowercase letter')
    if not re.search(r'[A-Z]', password):
        raise ValueError('Password must contain at least one uppercase letter')
    if not re.search(r'\d', password):
        raise ValueError('Password must contain at least one digit')
    if not re.search(r'[@$!%*?&^#()_+\-=\[\]{};:\'",.<>\\|`~]', password):
        raise ValueError('Password must contain at least one special character (@$!%*?&^#()_+-=[]{};\':\",./<>\\|`~)')
    return password


# ============ Authentication Models ============

class UserRegister(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username must be alphanumeric (underscores and hyphens allowed)')
        return v
    
    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        return validate_password_complexity(v)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserProfile(BaseModel):
    id: int
    email: str
    username: str
    is_admin: bool
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserProfileUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username must be alphanumeric (underscores and hyphens allowed)')
        return v


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
    
    @field_validator('new_password')
    @classmethod
    def password_complexity(cls, v):
        return validate_password_complexity(v)


# ============ User Webhook Models ============

class WebhookType(str, Enum):
    discord = "discord"
    slack = "slack"


class UserWebhookCreate(BaseModel):
    webhook_url: str = Field(..., min_length=10)
    webhook_name: str = Field(default="My Webhook", max_length=255)
    webhook_type: Optional[WebhookType] = None  # Auto-detected if not provided
    # Discord customization options
    bot_username: Optional[str] = Field(None, max_length=80)
    avatar_url: Optional[str] = None
    include_price: bool = True
    include_specs: bool = True
    mention_role_id: Optional[str] = Field(None, max_length=50)
    embed_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    # Slack-specific options
    slack_channel: Optional[str] = Field(None, max_length=100)
    
    @field_validator('webhook_url')
    @classmethod
    def validate_webhook_url(cls, v):
        if not v.startswith('https://'):
            raise ValueError('Webhook URL must use HTTPS')
        # Check for valid webhook providers
        valid_hosts = ['discord.com', 'discordapp.com', 'hooks.slack.com']
        if not any(host in v.lower() for host in valid_hosts):
            raise ValueError('Must be a valid Discord or Slack webhook URL')
        return v
    
    @field_validator('avatar_url')
    @classmethod
    def validate_avatar_url(cls, v):
        if v and not v.startswith('https://'):
            raise ValueError('Avatar URL must be HTTPS')
        return v


class UserWebhookUpdate(BaseModel):
    webhook_name: Optional[str] = Field(None, max_length=255)
    bot_username: Optional[str] = Field(None, max_length=80)
    avatar_url: Optional[str] = None
    include_price: Optional[bool] = None
    include_specs: Optional[bool] = None
    mention_role_id: Optional[str] = Field(None, max_length=50)
    embed_color: Optional[str] = Field(None, pattern=r'^#[0-9A-Fa-f]{6}$')
    slack_channel: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


class UserWebhook(BaseModel):
    id: int
    user_id: int
    webhook_url: str
    webhook_name: str
    webhook_type: str = "discord"
    bot_username: Optional[str] = None
    avatar_url: Optional[str] = None
    include_price: bool = True
    include_specs: bool = True
    mention_role_id: Optional[str] = None
    embed_color: Optional[str] = None
    slack_channel: Optional[str] = None
    is_active: bool
    created_at: datetime


# ============ User Plan Subscription Models ============

class PlanSubscriptionCreate(BaseModel):
    plan_code: str
    subsidiary: str = 'US'  # Default to US
    notify_on_available: bool = True


class PlanSubscriptionUpdate(BaseModel):
    notify_on_available: bool


class PlanSubscription(BaseModel):
    id: int
    user_id: int
    plan_code: str
    subsidiary: str
    notify_on_available: bool
    created_at: datetime
    # Joined fields from monitored_plans
    display_name: Optional[str] = None
    price: Optional[str] = None
    specs: Optional[str] = None


class BulkSubscriptionUpdate(BaseModel):
    """Update multiple plan subscriptions at once."""
    plan_codes: List[str]
    notify_on_available: bool = True


# ============ API Key Models ============

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    api_key: str  # Only returned on creation
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApiKeyInfo(BaseModel):
    id: int
    name: str
    last_used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: datetime


# ============ Admin Models ============

class AdminUserCreate(BaseModel):
    """Admin creates a new user."""
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)
    is_active: bool = True
    is_admin: bool = False
    
    @field_validator('username')
    @classmethod
    def username_alphanumeric(cls, v):
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Username must be alphanumeric (underscores and hyphens allowed)')
        return v
    
    @field_validator('password')
    @classmethod
    def password_complexity(cls, v):
        return validate_password_complexity(v)


class AdminUserUpdate(BaseModel):
    """Admin updates a user."""
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


class AdminUser(BaseModel):
    """User info for admin view."""
    id: int
    email: str
    username: str
    is_active: bool
    is_admin: bool
    created_at: datetime
    last_login: Optional[datetime] = None
    webhook_count: Optional[int] = None
    subscription_count: Optional[int] = None


# ============ Group Models ============

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


class Group(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_by: Optional[int] = None
    created_at: datetime
    member_count: Optional[int] = None


class GroupMemberAdd(BaseModel):
    user_id: int
    role: str = Field(default="member", pattern=r'^(owner|admin|member)$')


class GroupMember(BaseModel):
    user_id: int
    username: str
    email: str
    role: str
    joined_at: datetime


# ============ Config Models ============

class ConfigUpdate(BaseModel):
    key: str
    value: str


class DiscordWebhookConfig(BaseModel):
    webhook_url: str


class RegistrationToggle(BaseModel):
    allow_registration: bool


class CheckerSettings(BaseModel):
    """Checker agent configuration settings."""
    check_interval_seconds: int = Field(..., ge=30, le=3600, description="Check interval in seconds (30-3600)")
    notification_threshold_minutes: int = Field(..., ge=1, le=1440, description="Out-of-stock threshold before notifying (1-1440 minutes)")


class CheckerSettingsResponse(BaseModel):
    """Response for checker settings."""
    check_interval_seconds: int
    notification_threshold_minutes: int


class MonitoredPlanCreate(BaseModel):
    plan_code: str
    display_name: str
    url: str
    subsidiary: str = 'US'


class MonitoredPlanUpdate(BaseModel):
    enabled: bool


class MonitoredPlan(BaseModel):
    id: int
    plan_code: str
    subsidiary: str = 'US'
    display_name: Optional[str] = None
    url: str
    purchase_url: Optional[str] = None
    enabled: bool = True
    # Lifecycle tracking
    catalog_status: Optional[str] = None  # 'new', 'active', 'discontinued'
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    discontinued_at: Optional[datetime] = None
    # Visibility/orderable status
    is_orderable: Optional[bool] = True  # has 'order-funnel:show' tag
    visibility_tags: Optional[str] = None  # comma-separated tags
    # Specs
    vcpu: Optional[int] = None
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    storage_type: Optional[str] = None
    bandwidth_mbps: Optional[int] = None
    description: Optional[str] = None
    specs: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    created_at: datetime


class InventoryStatus(BaseModel):
    plan_code: str
    subsidiary: str = 'US'
    datacenter: str
    datacenter_code: Optional[str] = None
    is_available: bool
    linux_status: Optional[str] = None
    checked_at: datetime
    display_name: Optional[str] = None
    purchase_url: Optional[str] = None
    price: Optional[str] = None
    currency: Optional[str] = None
    out_of_stock_minutes: float = 0
    # Specs fields
    specs: Optional[str] = None
    vcpu: Optional[int] = None
    ram_gb: Optional[int] = None
    storage_gb: Optional[int] = None
    storage_type: Optional[str] = None
    bandwidth_mbps: Optional[int] = None
    plan_description: Optional[str] = None
    # Visibility/orderable status
    is_orderable: Optional[bool] = True
    product_line: Optional[str] = None
    # Location fields
    location_display_name: Optional[str] = None
    location_city: Optional[str] = None
    location_country: Optional[str] = None
    location_country_code: Optional[str] = None
    location_flag: Optional[str] = None
    location_region: Optional[str] = None


class StatusHistory(BaseModel):
    plan_code: str
    datacenter: str
    is_available: bool
    checked_at: datetime


class NotificationHistory(BaseModel):
    plan_code: str
    datacenter: str
    message: str
    sent_at: datetime
    success: bool
    error_message: Optional[str] = None


class TestWebhookResponse(BaseModel):
    success: bool
    message: Optional[str] = None


# ============ User Notification History ============

class UserNotificationHistory(BaseModel):
    id: int
    user_id: Optional[int] = None
    webhook_id: Optional[int] = None
    plan_code: str
    datacenter: str
    message: str
    sent_at: datetime
    success: bool
    error_message: Optional[str] = None
    is_default_webhook: bool = False
    message: str
