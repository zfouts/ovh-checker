-- ============================================================================
-- Migration: Add Slack Webhook Support
-- Date: 2026-01-20
-- ============================================================================

-- Add webhook_type column to user_webhooks
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'webhook_type'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN webhook_type VARCHAR(20) DEFAULT 'discord';
    END IF;
END $$;

-- Add additional Slack-specific columns if not exists
DO $$
BEGIN
    -- bot_username for customizing notification sender name
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'bot_username'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN bot_username VARCHAR(80) DEFAULT NULL;
    END IF;
    
    -- avatar_url for custom bot avatar
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'avatar_url'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN avatar_url TEXT DEFAULT NULL;
    END IF;
    
    -- include_price flag
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'include_price'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN include_price BOOLEAN DEFAULT TRUE;
    END IF;
    
    -- include_specs flag
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'include_specs'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN include_specs BOOLEAN DEFAULT TRUE;
    END IF;
    
    -- mention_role_id for Discord role pings
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'mention_role_id'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN mention_role_id VARCHAR(50) DEFAULT NULL;
    END IF;
    
    -- embed_color for Discord embed color
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'embed_color'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN embed_color VARCHAR(7) DEFAULT NULL;
    END IF;
    
    -- slack_channel for Slack channel override
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user_webhooks' AND column_name = 'slack_channel'
    ) THEN
        ALTER TABLE user_webhooks ADD COLUMN slack_channel VARCHAR(100) DEFAULT NULL;
    END IF;
END $$;

-- Create index on webhook_type for filtering
CREATE INDEX IF NOT EXISTS idx_user_webhooks_type ON user_webhooks(webhook_type);

-- Add comment
COMMENT ON COLUMN user_webhooks.webhook_type IS 'Type of webhook: discord, slack';
COMMENT ON COLUMN user_webhooks.slack_channel IS 'Optional Slack channel override (e.g., #alerts)';
