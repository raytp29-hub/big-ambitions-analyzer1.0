-- 003_smoke_test.sql
-- Check the permissions by acting as the app. Run as the OWNER, one statement at a time.

SET ROLE ba_app;                 -- from here on you are the app

INSERT INTO analytics.events (event_id, ts, session_id, host, app_version, event)
VALUES (gen_random_uuid(), now(), gen_random_uuid(), 'local', '3.0.0', 'session_start');
-- expected: INSERT 0 1

INSERT INTO analytics.events (event_id, ts, session_id, host, app_version, event)
VALUES (gen_random_uuid(), now(), gen_random_uuid(), 'local', '3.0.0', 'session_start')
ON CONFLICT DO NOTHING;
-- expected: INSERT 0 1 (DO NOTHING needs only INSERT)

SELECT * FROM analytics.events;  -- expected: ERROR: permission denied for table events
DELETE FROM analytics.events;    -- expected: ERROR: permission denied for table events

INSERT INTO analytics.events (event_id, ts, session_id, host, app_version, event)
VALUES (gen_random_uuid(), now(), gen_random_uuid(), 'mars', '3.0.0', 'session_start');
-- expected: ERROR: violates check constraint (host)

RESET ROLE;                      -- back to your own user

SELECT event_id, ts, received_at, host, event FROM analytics.events ORDER BY ts;
-- expected: the 2 rows inserted above

-- Clean up the test rows (as OWNER):
-- DELETE FROM analytics.events WHERE host = 'local';
