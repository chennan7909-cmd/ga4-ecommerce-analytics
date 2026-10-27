-- Export this result as CSV to data/raw/events.csv.
-- Full day partitions are required: observation_end passed to feature construction
-- is an exclusive UTC bound. This scope intentionally retains the original six events.
SELECT
  user_pseudo_id,
  (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS ga_session_id,
  TIMESTAMP_MICROS(event_timestamp) AS event_time,
  _TABLE_SUFFIX AS event_partition,
  event_name,
  device.category AS device,
  ecommerce.transaction_id AS transaction_id
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20210101' AND '20210131'
  AND event_name IN ('view_item', 'add_to_cart', 'begin_checkout',
                    'add_shipping_info', 'add_payment_info', 'purchase')
  AND user_pseudo_id IS NOT NULL
  AND (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') IS NOT NULL;
