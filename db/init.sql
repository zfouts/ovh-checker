-- OVH Checker Database Schema

-- Configuration table for Discord webhook and other settings
CREATE TABLE IF NOT EXISTS config (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ============================================================================
-- USERS TABLE (Multi-tenant Authentication)
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    is_admin BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_login_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- Datacenter locations mapping
CREATE TABLE IF NOT EXISTS datacenter_locations (
    datacenter_code VARCHAR(100) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    display_name VARCHAR(255),              -- Human readable name like "Brussels" or "Palo Alto"
    city VARCHAR(255) NOT NULL,
    country VARCHAR(255) NOT NULL,
    country_code VARCHAR(10),
    flag VARCHAR(10),
    region VARCHAR(50) NOT NULL,  -- US, EU, CA, APAC
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    PRIMARY KEY (datacenter_code, subsidiary)
);

CREATE INDEX IF NOT EXISTS idx_datacenter_locations_subsidiary ON datacenter_locations(subsidiary);

-- Products/plans to monitor
CREATE TABLE IF NOT EXISTS monitored_plans (
    id SERIAL PRIMARY KEY,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    display_name VARCHAR(255),
    url TEXT NOT NULL,
    purchase_url TEXT,
    enabled BOOLEAN DEFAULT TRUE,
    -- Lifecycle tracking
    catalog_status VARCHAR(50) DEFAULT 'active',  -- 'active', 'discontinued', 'new'
    first_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    discontinued_at TIMESTAMP WITH TIME ZONE,
    -- Visibility/orderable status from catalog tags
    is_orderable BOOLEAN DEFAULT TRUE,            -- has 'order-funnel:show' tag AND is 2025 line
    visibility_tags TEXT,                         -- comma-separated tags like 'order-funnel:show,website:show'
    product_line VARCHAR(50) DEFAULT 'legacy',    -- '2025' for new VPS 1-6, 'legacy' for older plans
    -- Specs from catalog API
    vcpu INTEGER,
    ram_gb INTEGER,
    storage_gb INTEGER,
    storage_type VARCHAR(100),
    bandwidth_mbps INTEGER,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(plan_code, subsidiary)
);

-- Plan pricing (fetched from OVH catalog API)
CREATE TABLE IF NOT EXISTS plan_pricing (
    id SERIAL PRIMARY KEY,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    commitment_months INTEGER NOT NULL DEFAULT 0,  -- 0 = no commitment, 6, 12, 24, etc.
    price_microcents BIGINT NOT NULL,  -- Price in microcents (divide by 100000000 to get dollars)
    currency VARCHAR(10) NOT NULL DEFAULT 'USD',
    description VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(plan_code, subsidiary, commitment_months)
);

CREATE INDEX IF NOT EXISTS idx_plan_pricing_plan_code ON plan_pricing(plan_code);
CREATE INDEX IF NOT EXISTS idx_plan_pricing_subsidiary ON plan_pricing(subsidiary);

-- ============================================================================
-- USER DISCORD WEBHOOKS (each user can have their own webhook with customization)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_webhooks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    webhook_name VARCHAR(255) DEFAULT 'My Discord',
    -- Discord customization options
    bot_username VARCHAR(80),           -- Custom bot display name (max 80 chars)
    avatar_url TEXT,                    -- Custom avatar URL
    include_price BOOLEAN DEFAULT TRUE, -- Include price in notifications
    include_specs BOOLEAN DEFAULT TRUE, -- Include specs in notifications
    mention_role_id VARCHAR(50),        -- Discord role ID to mention (e.g., @here, @everyone, or role ID)
    embed_color VARCHAR(10),            -- Hex color for embed (e.g., '#00ff00')
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_webhooks_user_id ON user_webhooks(user_id);

-- ============================================================================
-- GROUPS (for organizing users and shared alert configurations)
-- ============================================================================
CREATE TABLE IF NOT EXISTS groups (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- User-Group membership (many-to-many)
CREATE TABLE IF NOT EXISTS user_groups (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',  -- 'owner', 'admin', 'member'
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, group_id)
);

CREATE INDEX IF NOT EXISTS idx_user_groups_user_id ON user_groups(user_id);
CREATE INDEX IF NOT EXISTS idx_user_groups_group_id ON user_groups(group_id);

-- Group webhooks (shared webhooks for a group)
CREATE TABLE IF NOT EXISTS group_webhooks (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    webhook_name VARCHAR(255) DEFAULT 'Group Discord',
    bot_username VARCHAR(80),
    avatar_url TEXT,
    include_price BOOLEAN DEFAULT TRUE,
    include_specs BOOLEAN DEFAULT TRUE,
    mention_role_id VARCHAR(50),
    embed_color VARCHAR(10),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_group_webhooks_group_id ON group_webhooks(group_id);

-- Group plan subscriptions
CREATE TABLE IF NOT EXISTS group_plan_subscriptions (
    id SERIAL PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10),  -- NULL means all subsidiaries for this plan
    notify_on_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(group_id, plan_code, subsidiary)
);

CREATE INDEX IF NOT EXISTS idx_group_plan_subs_group_id ON group_plan_subscriptions(group_id);
CREATE INDEX IF NOT EXISTS idx_group_plan_subs_subsidiary ON group_plan_subscriptions(subsidiary);

-- ============================================================================
-- USER PLAN SUBSCRIPTIONS (which plans each user wants notifications for)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_plan_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10),  -- NULL means all subsidiaries for this plan
    notify_on_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, plan_code, subsidiary)
);

CREATE INDEX IF NOT EXISTS idx_user_plan_subs_user_id ON user_plan_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_plan_subs_plan_code ON user_plan_subscriptions(plan_code);
CREATE INDEX IF NOT EXISTS idx_user_plan_subs_subsidiary ON user_plan_subscriptions(subsidiary);

-- ============================================================================
-- USER NOTIFICATION HISTORY (track notifications per user)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_notification_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    webhook_id INTEGER REFERENCES user_webhooks(id) ON DELETE SET NULL,
    plan_code VARCHAR(255) NOT NULL,
    datacenter VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    is_default_webhook BOOLEAN DEFAULT FALSE  -- true if sent to system default webhook
);

CREATE INDEX IF NOT EXISTS idx_user_notif_history_user_id ON user_notification_history(user_id);
CREATE INDEX IF NOT EXISTS idx_user_notif_history_sent_at ON user_notification_history(sent_at);

-- ============================================================================
-- SESSION TOKENS (for JWT refresh tokens / revocation)
-- ============================================================================
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL UNIQUE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires ON refresh_tokens(expires_at);

-- ============================================================================
-- API KEYS (optional: for programmatic access)
-- ============================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);

-- Inventory status history
CREATE TABLE IF NOT EXISTS inventory_status (
    id SERIAL PRIMARY KEY,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    datacenter VARCHAR(100) NOT NULL,
    datacenter_code VARCHAR(100),
    is_available BOOLEAN NOT NULL,
    linux_status VARCHAR(50),
    raw_response JSONB,
    checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inventory_status_plan_code ON inventory_status(plan_code);
CREATE INDEX IF NOT EXISTS idx_inventory_status_checked_at ON inventory_status(checked_at);
CREATE INDEX IF NOT EXISTS idx_inventory_status_subsidiary ON inventory_status(subsidiary);

-- Track when items go out of stock
CREATE TABLE IF NOT EXISTS out_of_stock_tracking (
    id SERIAL PRIMARY KEY,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    datacenter VARCHAR(100) NOT NULL,
    out_of_stock_since TIMESTAMP WITH TIME ZONE NOT NULL,
    notified BOOLEAN DEFAULT FALSE,
    returned_to_stock_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(plan_code, subsidiary, datacenter, out_of_stock_since)
);

CREATE INDEX IF NOT EXISTS idx_out_of_stock_tracking_plan_dc ON out_of_stock_tracking(plan_code, datacenter);
CREATE INDEX IF NOT EXISTS idx_out_of_stock_tracking_subsidiary ON out_of_stock_tracking(subsidiary);

-- Notification history (system default webhook)
CREATE TABLE IF NOT EXISTS notification_history (
    id SERIAL PRIMARY KEY,
    plan_code VARCHAR(255) NOT NULL,
    subsidiary VARCHAR(10) NOT NULL DEFAULT 'US',  -- OVH subsidiary (US, FR, CA, etc.)
    datacenter VARCHAR(100) NOT NULL,
    message TEXT NOT NULL,
    sent_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    is_default_webhook BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS idx_notification_history_subsidiary ON notification_history(subsidiary);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_inventory_status_plan_code ON inventory_status(plan_code);
CREATE INDEX IF NOT EXISTS idx_inventory_status_checked_at ON inventory_status(checked_at);
CREATE INDEX IF NOT EXISTS idx_out_of_stock_tracking_plan_dc ON out_of_stock_tracking(plan_code, datacenter);

-- Insert default config values (no webhook URL by default - must be configured)
INSERT INTO config (key, value) VALUES ('discord_webhook_url', '') ON CONFLICT (key) DO NOTHING;
INSERT INTO config (key, value) VALUES ('notification_threshold_minutes', '60') ON CONFLICT (key) DO NOTHING;
INSERT INTO config (key, value) VALUES ('check_interval_seconds', '120') ON CONFLICT (key) DO NOTHING;
INSERT INTO config (key, value) VALUES ('pricing_last_updated', '') ON CONFLICT (key) DO NOTHING;
INSERT INTO config (key, value) VALUES ('catalog_last_synced', '') ON CONFLICT (key) DO NOTHING;
-- Comma-separated list of subsidiaries to monitor (e.g., 'US,FR,CA,DE' or 'ALL' for all)
INSERT INTO config (key, value) VALUES ('monitored_subsidiaries', 'US,CA,FR,DE,GB') ON CONFLICT (key) DO NOTHING;
INSERT INTO config (key, value) VALUES ('allow_registration', 'true') ON CONFLICT (key) DO NOTHING;

-- NOTE: Admin user is bootstrapped on first API startup with a random password.
-- Check the API logs for the generated credentials.

-- NOTE: All data is now auto-discovered from OVH APIs:
--   - monitored_plans: Synced per subsidiary from Order Catalog API with specs and pricing
--   - datacenter_locations: Synced from catalog (city/country) with code mappings from availability API
-- Datacenter seed data removed - all locations are now auto-discovered from each subsidiary's catalog
