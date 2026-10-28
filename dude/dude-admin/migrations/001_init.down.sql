BEGIN;

DROP TABLE IF EXISTS admin_request_logs;
DROP TABLE IF EXISTS admin_refresh_tokens;
DROP TABLE IF EXISTS admin_token_usage;
DROP TABLE IF EXISTS admin_model_configs;
DROP TABLE IF EXISTS admin_users;

COMMIT;
