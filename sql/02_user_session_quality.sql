-- January 2021 identity and session-key quality for the same six e-commerce
-- events as 01_event_coverage.sql.
-- A valid session requires both user_pseudo_id and ga_session_id. Because
-- ga_session_id is not globally unique, a session is the distinct pair of
-- (user_pseudo_id, ga_session_id).

WITH scoped_events AS (
  SELECT
    event_name,
    user_pseudo_id,
    (
      SELECT value.int_value
      FROM UNNEST(event_params)
      WHERE key = 'ga_session_id'
    ) AS ga_session_id
  FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
  WHERE _TABLE_SUFFIX BETWEEN '20210101' AND '20210131'
    AND event_name IN (
      'view_item',
      'add_to_cart',
      'begin_checkout',
      'add_shipping_info',
      'add_payment_info',
      'purchase'
    )
),
valid_sessions AS (
  SELECT DISTINCT
    user_pseudo_id,
    ga_session_id
  FROM scoped_events
  WHERE user_pseudo_id IS NOT NULL
    AND ga_session_id IS NOT NULL
)
SELECT
  COUNT(*) AS event_rows,
  COUNTIF(user_pseudo_id IS NULL) AS missing_user_pseudo_id_rows,
  SAFE_DIVIDE(COUNTIF(user_pseudo_id IS NULL), COUNT(*)) AS missing_user_pseudo_id_rate,
  COUNTIF(ga_session_id IS NULL) AS missing_ga_session_id_rows,
  SAFE_DIVIDE(COUNTIF(ga_session_id IS NULL), COUNT(*)) AS missing_ga_session_id_rate,
  COUNTIF(user_pseudo_id IS NULL OR ga_session_id IS NULL) AS invalid_session_key_rows,
  SAFE_DIVIDE(
    COUNTIF(user_pseudo_id IS NULL OR ga_session_id IS NULL),
    COUNT(*)
  ) AS invalid_session_key_rate,
  COUNTIF(user_pseudo_id IS NOT NULL AND ga_session_id IS NOT NULL) AS valid_session_event_rows,
  (SELECT COUNT(*) FROM valid_sessions) AS valid_sessions
FROM scoped_events;
