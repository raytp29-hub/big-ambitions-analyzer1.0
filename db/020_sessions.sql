-- 020_sessions.sql
-- One row per session, built only from stg_events.
-- GROUP BY includes host and app_version: a session with two versions would show up
-- as two rows (visible anomaly) instead of being hidden by an aggregate.
-- HAVING drops sessions where nothing happened besides session_start.
-- Run as the database OWNER, after 010_stg_events.sql.

CREATE OR REPLACE VIEW analytics.sessions AS
SELECT
    session_id,
    host,
    app_version,
    min(ts)                                                 AS started_at,
    max(ts)                                                 AS ended_at,
    max(ts) - min(ts)                                       AS duration,
    extract(epoch FROM max(ts) - min(ts))                   AS duration_s,
    count(*)                                                AS n_events,
    count(*) FILTER (WHERE event = 'page_view')             AS n_page_views,
    bool_or(event = 'file_loaded')                          AS loaded_file,
    bool_or(event = 'page_view' AND page = 'health_check')  AS visited_health_check,
    bool_or(event = 'optimize_clicked')                     AS clicked_optimize,
    bool_or(event = 'feedback_sent')                        AS sent_feedback
FROM analytics.stg_events
GROUP BY session_id, host, app_version
HAVING bool_or(event <> 'session_start');

-- Check:
-- SELECT * FROM analytics.sessions ORDER BY started_at;