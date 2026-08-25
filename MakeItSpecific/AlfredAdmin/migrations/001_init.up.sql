-- Alfred Admin Database Schema (Go-managed tables)
-- Prefixed with "admin_" to avoid collisions with Python-managed Alfred tables.
-- All tables use IF NOT EXISTS for safe co-existence with Alfred's _init_db().

BEGIN;

-- ============================================================
-- Migration Version Tracking
-- Records which migrations have been applied, preventing re-execution.
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_schema_migrations (
    version     VARCHAR(64) PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- Users
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(64) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role          VARCHAR(16) NOT NULL DEFAULT 'user' CHECK (role IN ('admin', 'user')),
    is_active     BOOLEAN NOT NULL DEFAULT true,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_username ON admin_users (username);
CREATE INDEX IF NOT EXISTS idx_admin_users_role ON admin_users (role);

-- ============================================================
-- Model Configs — stores provider/model info, NOT API keys
-- Python reads this table to resolve model configs at LLM call time
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_model_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    alias           VARCHAR(64) UNIQUE NOT NULL,
    provider        VARCHAR(32) NOT NULL,
    model_name      VARCHAR(128) NOT NULL,
    base_url        VARCHAR(512) NOT NULL,
    api_key_env_var VARCHAR(64) NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT false,
    is_enabled      BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_model_configs_alias ON admin_model_configs (alias);
CREATE INDEX IF NOT EXISTS idx_admin_model_configs_provider ON admin_model_configs (provider);

-- ============================================================
-- Token Usage — per-LLM-call tracking
-- Go admin reads this; Python writes this asynchronously
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_token_usage (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    session_id      VARCHAR(64) DEFAULT '',  -- matches Alfred sessions.id (UUID string, 36 chars)
    provider        VARCHAR(32) NOT NULL,
    model_name      VARCHAR(128) NOT NULL,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    duration_ms     DOUBLE PRECISION NOT NULL DEFAULT 0,
    success         BOOLEAN NOT NULL DEFAULT true,
    error_message   TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_token_usage_user ON admin_token_usage (user_id);
CREATE INDEX IF NOT EXISTS idx_admin_token_usage_created ON admin_token_usage (created_at);
CREATE INDEX IF NOT EXISTS idx_admin_token_usage_model ON admin_token_usage (provider, model_name);

-- ============================================================
-- Refresh Tokens — stored in PostgreSQL (no Redis)
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(128) NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_refresh_user ON admin_refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_admin_refresh_hash ON admin_refresh_tokens (token_hash);

-- ============================================================
-- Request Logs — per-request tracking
-- ============================================================
CREATE TABLE IF NOT EXISTS admin_request_logs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID REFERENCES admin_users(id) ON DELETE SET NULL,
    method          VARCHAR(8) NOT NULL,
    path            VARCHAR(512) NOT NULL,
    status_code     INTEGER NOT NULL,
    duration_ms     BIGINT NOT NULL DEFAULT 0,
    client_ip       VARCHAR(64) DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admin_request_logs_user ON admin_request_logs (user_id);
CREATE INDEX IF NOT EXISTS idx_admin_request_logs_created ON admin_request_logs (created_at);

COMMIT;
