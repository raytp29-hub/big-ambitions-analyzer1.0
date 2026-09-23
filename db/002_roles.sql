-- 002_roles.sql
-- Least privilege: the app can only INSERT events. It cannot read, update or delete.
-- Run as the database OWNER.
-- Replace CHANGE_ME before running. Never commit a real password.

CREATE ROLE ba_app LOGIN PASSWORD 'CHANGE_ME' CONNECTION LIMIT 5;

-- Three doors, checked in order: database -> schema -> table.
GRANT CONNECT ON DATABASE ba_analytics TO ba_app;   -- adjust the name on Neon
GRANT USAGE   ON SCHEMA analytics      TO ba_app;
GRANT INSERT  ON analytics.events      TO ba_app;

-- Rotate the password if the connection string leaks:
-- ALTER ROLE ba_app PASSWORD 'new-password';
