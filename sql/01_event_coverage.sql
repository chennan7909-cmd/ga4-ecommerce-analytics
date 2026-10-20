-- January 2021 coverage for the six e-commerce events used by this project.
-- Output schema: event_name STRING, event_count INT64, users INT64.
-- `users` counts distinct non-NULL user_pseudo_id values independently for
-- each event; this query does not calculate a sequential funnel.

WITH target_events AS (
  SELECT *
  FROM UNNEST([
    STRUCT(1 AS step_order, 'view_item' AS event_name),
    STRUCT(2 AS step_order, 'add_to_cart' AS event_name),
    STRUCT(3 AS step_order, 'begin_checkout' AS event_name),
    STRUCT(4 AS step_order, 'add_shipping_info' AS event_name),
    STRUCT(5 AS step_order, 'add_payment_info' AS event_name),
    STRUCT(6 AS step_order, 'purchase' AS event_name)
  ])
),
january_events AS (
  SELECT
    event_name,
    user_pseudo_id
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
)
SELECT
  target.event_name,
  COUNT(events.event_name) AS event_count,
  COUNT(DISTINCT events.user_pseudo_id) AS users
FROM target_events AS target
LEFT JOIN january_events AS events
  ON target.event_name = events.event_name
GROUP BY
  target.step_order,
  target.event_name
ORDER BY target.step_order;
