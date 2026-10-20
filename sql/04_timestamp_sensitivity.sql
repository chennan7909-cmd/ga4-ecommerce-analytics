-- RUN OUTPUT RECORDED IN results/timestamp_sensitivity_2021-01.csv.
-- Timestamp-order sensitivity analysis for the January 2021 session funnel.
--
-- The strict `>` path remains the primary metric. The relaxed `>=` path is a
-- permissive comparison only: it allows adjacent steps at the same timestamp
-- but cannot prove their real order. Both paths independently select the
-- earliest event that satisfies the prior step's timestamp condition.
--
-- Counting unit: a valid (user_pseudo_id, ga_session_id) session.
-- Entry population: valid sessions containing view_item.
-- Path: view_item -> add_to_cart -> begin_checkout -> purchase.
-- This is session-level and does not require the same item at every step.

CREATE TEMP TABLE valid_events AS
WITH scoped_events AS (
  SELECT
    event_name,
    event_timestamp,
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
      'purchase'
    )
)
SELECT *
FROM scoped_events
WHERE user_pseudo_id IS NOT NULL
  AND ga_session_id IS NOT NULL;

CREATE TEMP TABLE entry_sessions AS
SELECT
  user_pseudo_id,
  ga_session_id,
  MIN(event_timestamp) AS view_item_ts
FROM valid_events
WHERE event_name = 'view_item'
GROUP BY
  user_pseudo_id,
  ga_session_id;

CREATE TEMP TABLE strict_session_steps AS
WITH add_to_cart_steps AS (
  SELECT
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.view_item_ts,
    MIN(events.event_timestamp) AS add_to_cart_ts
  FROM entry_sessions AS entry
  INNER JOIN valid_events AS events
    ON entry.user_pseudo_id = events.user_pseudo_id
    AND entry.ga_session_id = events.ga_session_id
    AND events.event_name = 'add_to_cart'
    AND events.event_timestamp > entry.view_item_ts
  GROUP BY
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.view_item_ts
),
begin_checkout_steps AS (
  SELECT
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.view_item_ts,
    cart.add_to_cart_ts,
    MIN(events.event_timestamp) AS begin_checkout_ts
  FROM add_to_cart_steps AS cart
  INNER JOIN valid_events AS events
    ON cart.user_pseudo_id = events.user_pseudo_id
    AND cart.ga_session_id = events.ga_session_id
    AND events.event_name = 'begin_checkout'
    AND events.event_timestamp > cart.add_to_cart_ts
  GROUP BY
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.view_item_ts,
    cart.add_to_cart_ts
),
purchase_steps AS (
  SELECT
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts,
    MIN(events.event_timestamp) AS purchase_ts
  FROM begin_checkout_steps AS checkout
  INNER JOIN valid_events AS events
    ON checkout.user_pseudo_id = events.user_pseudo_id
    AND checkout.ga_session_id = events.ga_session_id
    AND events.event_name = 'purchase'
    AND events.event_timestamp > checkout.begin_checkout_ts
  GROUP BY
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts
)
SELECT
  entry.user_pseudo_id,
  entry.ga_session_id,
  entry.view_item_ts,
  cart.add_to_cart_ts,
  checkout.begin_checkout_ts,
  purchase.purchase_ts
FROM entry_sessions AS entry
LEFT JOIN add_to_cart_steps AS cart
  USING (user_pseudo_id, ga_session_id, view_item_ts)
LEFT JOIN begin_checkout_steps AS checkout
  USING (user_pseudo_id, ga_session_id, view_item_ts, add_to_cart_ts)
LEFT JOIN purchase_steps AS purchase
  USING (
    user_pseudo_id,
    ga_session_id,
    view_item_ts,
    add_to_cart_ts,
    begin_checkout_ts
  );

CREATE TEMP TABLE relaxed_session_steps AS
WITH add_to_cart_steps AS (
  SELECT
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.view_item_ts,
    MIN(events.event_timestamp) AS add_to_cart_ts
  FROM entry_sessions AS entry
  INNER JOIN valid_events AS events
    ON entry.user_pseudo_id = events.user_pseudo_id
    AND entry.ga_session_id = events.ga_session_id
    AND events.event_name = 'add_to_cart'
    AND events.event_timestamp >= entry.view_item_ts
  GROUP BY
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.view_item_ts
),
begin_checkout_steps AS (
  SELECT
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.view_item_ts,
    cart.add_to_cart_ts,
    MIN(events.event_timestamp) AS begin_checkout_ts
  FROM add_to_cart_steps AS cart
  INNER JOIN valid_events AS events
    ON cart.user_pseudo_id = events.user_pseudo_id
    AND cart.ga_session_id = events.ga_session_id
    AND events.event_name = 'begin_checkout'
    AND events.event_timestamp >= cart.add_to_cart_ts
  GROUP BY
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.view_item_ts,
    cart.add_to_cart_ts
),
purchase_steps AS (
  SELECT
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts,
    MIN(events.event_timestamp) AS purchase_ts
  FROM begin_checkout_steps AS checkout
  INNER JOIN valid_events AS events
    ON checkout.user_pseudo_id = events.user_pseudo_id
    AND checkout.ga_session_id = events.ga_session_id
    AND events.event_name = 'purchase'
    AND events.event_timestamp >= checkout.begin_checkout_ts
  GROUP BY
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts
)
SELECT
  entry.user_pseudo_id,
  entry.ga_session_id,
  entry.view_item_ts,
  cart.add_to_cart_ts,
  checkout.begin_checkout_ts,
  purchase.purchase_ts
FROM entry_sessions AS entry
LEFT JOIN add_to_cart_steps AS cart
  USING (user_pseudo_id, ga_session_id, view_item_ts)
LEFT JOIN begin_checkout_steps AS checkout
  USING (user_pseudo_id, ga_session_id, view_item_ts, add_to_cart_ts)
LEFT JOIN purchase_steps AS purchase
  USING (
    user_pseudo_id,
    ga_session_id,
    view_item_ts,
    add_to_cart_ts,
    begin_checkout_ts
  );

-- One comparison row per funnel step. The purchase row compares complete
-- four-step paths under the strict and relaxed timestamp rules.
WITH strict_counts AS (
  SELECT 1 AS step_order, 'view_item' AS step_name, COUNT(*) AS sessions
  FROM strict_session_steps
  UNION ALL
  SELECT 2, 'add_to_cart', COUNTIF(add_to_cart_ts IS NOT NULL)
  FROM strict_session_steps
  UNION ALL
  SELECT 3, 'begin_checkout', COUNTIF(begin_checkout_ts IS NOT NULL)
  FROM strict_session_steps
  UNION ALL
  SELECT 4, 'purchase', COUNTIF(purchase_ts IS NOT NULL)
  FROM strict_session_steps
),
relaxed_counts AS (
  SELECT 1 AS step_order, 'view_item' AS step_name, COUNT(*) AS sessions
  FROM relaxed_session_steps
  UNION ALL
  SELECT 2, 'add_to_cart', COUNTIF(add_to_cart_ts IS NOT NULL)
  FROM relaxed_session_steps
  UNION ALL
  SELECT 3, 'begin_checkout', COUNTIF(begin_checkout_ts IS NOT NULL)
  FROM relaxed_session_steps
  UNION ALL
  SELECT 4, 'purchase', COUNTIF(purchase_ts IS NOT NULL)
  FROM relaxed_session_steps
),
comparison AS (
  SELECT
    strict.step_order,
    strict.step_name,
    strict.sessions AS strict_sessions,
    relaxed.sessions AS relaxed_sessions,
    LAG(strict.sessions) OVER (ORDER BY strict.step_order) AS strict_previous_sessions,
    LAG(relaxed.sessions) OVER (ORDER BY strict.step_order) AS relaxed_previous_sessions,
    FIRST_VALUE(strict.sessions) OVER (ORDER BY strict.step_order) AS strict_entry_sessions,
    FIRST_VALUE(relaxed.sessions) OVER (ORDER BY strict.step_order) AS relaxed_entry_sessions
  FROM strict_counts AS strict
  INNER JOIN relaxed_counts AS relaxed
    USING (step_order, step_name)
)
SELECT
  step_order,
  step_name,
  strict_sessions,
  relaxed_sessions,
  relaxed_sessions - strict_sessions AS relaxed_minus_strict_sessions,
  SAFE_DIVIDE(strict_sessions, strict_previous_sessions) AS strict_adjacent_conversion,
  SAFE_DIVIDE(relaxed_sessions, relaxed_previous_sessions) AS relaxed_adjacent_conversion,
  SAFE_DIVIDE(strict_sessions, strict_entry_sessions) AS strict_conversion_from_entry,
  SAFE_DIVIDE(relaxed_sessions, relaxed_entry_sessions) AS relaxed_conversion_from_entry
FROM comparison
ORDER BY step_order;
