-- 010_stg_events.sql
-- Staging: one clean, typed row per event. Downstream views never read props directly.
-- event_date = UTC day: <il tuo motivo>
-- Run as the database OWNER.

CREATE OR REPLACE VIEW analytics.stg_events AS
SELECT
    event_id,
    ts,
    (ts AT TIME ZONE 'UTC')::date                               AS event_date,
    session_id,
    host,
    app_version,
    event,
    page,
    props ->> 'source'                                          AS source,
    (props ->> 'n_businesses')::int                             AS n_businesses,
    replace(props ->> 'business_type', 'ba:businesstype_', '')  AS business_type,
    (props ->> 'rating')::smallint                              AS rating,
    props -> 'topics'                                           AS topics,
    props ->> 'other_text'                                      AS other_text
FROM analytics.events;

-- Check:
-- SELECT event, source, n_businesses, business_type, rating, topics
-- FROM analytics.stg_events
-- WHERE event NOT IN ('page_view', 'session_start')
-- ORDER BY ts;