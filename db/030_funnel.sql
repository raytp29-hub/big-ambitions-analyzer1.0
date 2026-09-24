-- 030_funnel.sql
-- Closed funnel per host: a step counts only if the previous steps happened too.
-- Percentages are on the previous step (where users drop), not on the total.
-- Run as the database OWNER, after 020_sessions.sql.

CREATE OR REPLACE VIEW analytics.funnel AS
SELECT
    host,
    count(*)                                                                      AS n_sessions,
    count(*) FILTER (WHERE loaded_file)                                           AS n_loaded,
    count(*) FILTER (WHERE loaded_file AND visited_health_check)                  AS n_health_check,
    count(*) FILTER (WHERE loaded_file AND visited_health_check AND clicked_optimize) AS n_optimize,
    round(100.0 * count(*) FILTER (WHERE loaded_file)
          / NULLIF(count(*), 0), 1)                                               AS pct_loaded,
    round(100.0 * count(*) FILTER (WHERE loaded_file AND visited_health_check)
          / NULLIF(count(*) FILTER (WHERE loaded_file), 0), 1)                    AS pct_health_check,
    round(100.0 * count(*) FILTER (WHERE loaded_file AND visited_health_check AND clicked_optimize)
          / NULLIF(count(*) FILTER (WHERE loaded_file AND visited_health_check), 0), 1) AS pct_optimize
FROM analytics.sessions
GROUP BY host;

-- Check:
SELECT * FROM analytics.funnel;