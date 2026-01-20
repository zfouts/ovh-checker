-- Migration: Add authentication and multi-tenancy support
-- OVH Checker - Production Ready Multi-Tenant Update

-- ============================================================================
-- USERS TABLE
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

-- ============================================================================
-- USER DISCORD WEBHOOKS (each user can have their own webhook)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_webhooks (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    webhook_url TEXT NOT NULL,
    webhook_name VARCHAR(255) DEFAULT 'My Discord',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_webhooks_user_id ON user_webhooks(user_id);

-- ============================================================================
-- USER PLAN SUBSCRIPTIONS (which plans each user wants notifications for)
-- ============================================================================
CREATE TABLE IF NOT EXISTS user_plan_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_code VARCHAR(255) NOT NULL REFERENCES monitored_plans(plan_code) ON DELETE CASCADE,
    notify_on_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(user_id, plan_code)
);

CREATE INDEX IF NOT EXISTS idx_user_plan_subs_user_id ON user_plan_subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_plan_subs_plan_code ON user_plan_subscriptions(plan_code);

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

-- ============================================================================
-- UPDATE NOTIFICATION HISTORY TO SUPPORT DEFAULT VS USER WEBHOOKS
-- ============================================================================
-- Add column to existing notification_history if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'notification_history' AND column_name = 'is_default_webhook'
    ) THEN
        ALTER TABLE notification_history ADD COLUMN is_default_webhook BOOLEAN DEFAULT TRUE;
    END IF;
END $$;

-- ============================================================================
-- DEFAULT ADMIN USER (password: changeme - MUST be changed in production!)
-- ============================================================================
-- Password hash for 'changeme' using bcrypt
-- You should change this immediately after deployment
INSERT INTO users (email, username, password_hash, is_active, is_admin)
VALUES (
    'admin@example.com', 
    'admin', 
    '$2b$12$NrsJtLEanYtMj2Vz1ZC7vuM.qEM/MdIsyXR2v/GVVWcoHuXi0ksuC',  -- 'changeme'
    TRUE, 
    TRUE
)
ON CONFLICT (email) DO NOTHING;

