-- RUN OUTPUTS RECORDED IN results/device_*_2021-01.csv.
-- January 2021 strict sequential session funnel grouped by session-level
-- device category.
--
-- Source scope: the six defined shopping events. A valid session is the pair
-- (user_pseudo_id, ga_session_id). Device assignment is fixed once per valid
-- shopping session before any funnel aggregation:
--   * one distinct nonempty category -> that category;
--   * no nonempty category -> unknown;
--   * more than one distinct nonempty category -> mixed.
-- No category is filtered, and no session is assigned to multiple categories.
--
-- The strict funnel selects the earliest event strictly later than the chosen
-- prior step. It is session-level and does not require the same item at every
-- step. The script returns three result sets, each with an all_devices total
-- row for reconciliation. Previously recorded totals are not embedded in the
-- calculation logic.

-- One source scan materializes all valid rows used by the three result sets.
CREATE TEMP TABLE valid_shopping_events AS
WITH extracted_events AS (
  SELECT
    event_name,
    event_timestamp,
    user_pseudo_id,
    (
      SELECT value.int_value
      FROM UNNEST(event_params)
      WHERE key = 'ga_session_id'
    ) AS ga_session_id,
    NULLIF(TRIM(device.category), '') AS nonempty_device_category
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
SELECT *
FROM extracted_events
WHERE user_pseudo_id IS NOT NULL
  AND ga_session_id IS NOT NULL;

-- Exactly one row per valid shopping session. MAX is deterministic here only
-- when the distinct nonempty category count is one; it is never used to choose
-- among multiple categories.
CREATE TEMP TABLE session_device_assignment AS
WITH session_device_profile AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    COUNT(*) AS valid_shopping_event_rows,
    COUNTIF(nonempty_device_category IS NULL) AS missing_device_category_event_rows,
    COUNT(DISTINCT nonempty_device_category) AS distinct_nonempty_device_categories,
    MAX(nonempty_device_category) AS sole_nonempty_device_category
  FROM valid_shopping_events
  GROUP BY
    user_pseudo_id,
    ga_session_id
)
SELECT
  user_pseudo_id,
  ga_session_id,
  CASE
    WHEN distinct_nonempty_device_categories = 0 THEN 'unknown'
    WHEN distinct_nonempty_device_categories = 1 THEN sole_nonempty_device_category
    ELSE 'mixed'
  END AS device_category,
  valid_shopping_event_rows,
  missing_device_category_event_rows,
  distinct_nonempty_device_categories
FROM session_device_profile;

-- Strict ordered path, with one row per valid entry session.
CREATE TEMP TABLE strict_session_steps AS
WITH entry_sessions AS (
  SELECT
    events.user_pseudo_id,
    events.ga_session_id,
    assignment.device_category,
    MIN(events.event_timestamp) AS view_item_ts
  FROM valid_shopping_events AS events
  INNER JOIN session_device_assignment AS assignment
    USING (user_pseudo_id, ga_session_id)
  WHERE events.event_name = 'view_item'
  GROUP BY
    events.user_pseudo_id,
    events.ga_session_id,
    assignment.device_category
),
add_to_cart_steps AS (
  SELECT
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.device_category,
    entry.view_item_ts,
    MIN(events.event_timestamp) AS add_to_cart_ts
  FROM entry_sessions AS entry
  INNER JOIN valid_shopping_events AS events
    ON entry.user_pseudo_id = events.user_pseudo_id
    AND entry.ga_session_id = events.ga_session_id
    AND events.event_name = 'add_to_cart'
    AND events.event_timestamp > entry.view_item_ts
  GROUP BY
    entry.user_pseudo_id,
    entry.ga_session_id,
    entry.device_category,
    entry.view_item_ts
),
begin_checkout_steps AS (
  SELECT
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.device_category,
    cart.view_item_ts,
    cart.add_to_cart_ts,
    MIN(events.event_timestamp) AS begin_checkout_ts
  FROM add_to_cart_steps AS cart
  INNER JOIN valid_shopping_events AS events
    ON cart.user_pseudo_id = events.user_pseudo_id
    AND cart.ga_session_id = events.ga_session_id
    AND events.event_name = 'begin_checkout'
    AND events.event_timestamp > cart.add_to_cart_ts
  GROUP BY
    cart.user_pseudo_id,
    cart.ga_session_id,
    cart.device_category,
    cart.view_item_ts,
    cart.add_to_cart_ts
),
purchase_steps AS (
  SELECT
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.device_category,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts,
    MIN(events.event_timestamp) AS purchase_ts
  FROM begin_checkout_steps AS checkout
  INNER JOIN valid_shopping_events AS events
    ON checkout.user_pseudo_id = events.user_pseudo_id
    AND checkout.ga_session_id = events.ga_session_id
    AND events.event_name = 'purchase'
    AND events.event_timestamp > checkout.begin_checkout_ts
  GROUP BY
    checkout.user_pseudo_id,
    checkout.ga_session_id,
    checkout.device_category,
    checkout.view_item_ts,
    checkout.add_to_cart_ts,
    checkout.begin_checkout_ts
)
SELECT
  entry.user_pseudo_id,
  entry.ga_session_id,
  entry.device_category,
  entry.view_item_ts,
  cart.add_to_cart_ts,
  checkout.begin_checkout_ts,
  purchase.purchase_ts
FROM entry_sessions AS entry
LEFT JOIN add_to_cart_steps AS cart
  USING (user_pseudo_id, ga_session_id, device_category, view_item_ts)
LEFT JOIN begin_checkout_steps AS checkout
  USING (
    user_pseudo_id,
    ga_session_id,
    device_category,
    view_item_ts,
    add_to_cart_ts
  )
LEFT JOIN purchase_steps AS purchase
  USING (
    user_pseudo_id,
    ga_session_id,
    device_category,
    view_item_ts,
    add_to_cart_ts,
    begin_checkout_ts
  );

-- Result set 1: device assignment quality.
-- Event-row fields count valid shopping event rows. Session fields count
-- distinct valid shopping sessions after the one-row assignment above.
WITH quality_by_device AS (
  SELECT
    device_category,
    COUNT(*) AS valid_shopping_sessions,
    SUM(valid_shopping_event_rows) AS valid_shopping_event_rows,
    SUM(missing_device_category_event_rows) AS missing_device_category_event_rows,
    COUNTIF(missing_device_category_event_rows > 0) AS sessions_with_missing_device_category,
    COUNTIF(
      distinct_nonempty_device_categories > 1
    ) AS sessions_with_multiple_nonempty_device_categories
  FROM session_device_assignment
  GROUP BY device_category
),
quality_output AS (
  SELECT
    'device' AS row_type,
    device_category,
    valid_shopping_sessions,
    valid_shopping_event_rows,
    missing_device_category_event_rows,
    sessions_with_missing_device_category,
    sessions_with_multiple_nonempty_device_categories
  FROM quality_by_device

  UNION ALL

  SELECT
    'all_devices',
    CAST(NULL AS STRING),
    SUM(valid_shopping_sessions),
    SUM(valid_shopping_event_rows),
    SUM(missing_device_category_event_rows),
    SUM(sessions_with_missing_device_category),
    SUM(sessions_with_multiple_nonempty_device_categories)
  FROM quality_by_device
)
SELECT *
FROM quality_output
ORDER BY
  CASE row_type WHEN 'device' THEN 1 ELSE 2 END,
  device_category;

-- Result set 2: strict sequential funnel by assigned session device.
-- Every observed device category receives four rows, including zero steps.
WITH device_categories AS (
  SELECT DISTINCT device_category
  FROM session_device_assignment
),
steps AS (
  SELECT *
  FROM UNNEST([
    STRUCT(1 AS step_order, 'view_item' AS step_name),
    STRUCT(2 AS step_order, 'add_to_cart' AS step_name),
    STRUCT(3 AS step_order, 'begin_checkout' AS step_name),
    STRUCT(4 AS step_order, 'purchase' AS step_name)
  ])
),
funnel_by_device AS (
  SELECT
    device_category,
    COUNT(*) AS view_item_sessions,
    COUNTIF(add_to_cart_ts IS NOT NULL) AS add_to_cart_sessions,
    COUNTIF(begin_checkout_ts IS NOT NULL) AS begin_checkout_sessions,
    COUNTIF(purchase_ts IS NOT NULL) AS purchase_sessions
  FROM strict_session_steps
  GROUP BY device_category
),
device_step_counts AS (
  SELECT
    categories.device_category,
    steps.step_order,
    steps.step_name,
    CASE steps.step_order
      WHEN 1 THEN COALESCE(funnel.view_item_sessions, 0)
      WHEN 2 THEN COALESCE(funnel.add_to_cart_sessions, 0)
      WHEN 3 THEN COALESCE(funnel.begin_checkout_sessions, 0)
      WHEN 4 THEN COALESCE(funnel.purchase_sessions, 0)
    END AS sessions
  FROM device_categories AS categories
  CROSS JOIN steps
  LEFT JOIN funnel_by_device AS funnel
    USING (device_category)
),
all_device_step_counts AS (
  SELECT
    step_order,
    step_name,
    SUM(sessions) AS sessions
  FROM device_step_counts
  GROUP BY
    step_order,
    step_name
),
combined_step_counts AS (
  SELECT
    'device' AS row_type,
    device_category,
    step_order,
    step_name,
    sessions
  FROM device_step_counts

  UNION ALL

  SELECT
    'all_devices',
    CAST(NULL AS STRING),
    step_order,
    step_name,
    sessions
  FROM all_device_step_counts
),
with_comparisons AS (
  SELECT
    row_type,
    device_category,
    step_order,
    step_name,
    sessions,
    LAG(sessions) OVER (
      PARTITION BY row_type, device_category
      ORDER BY step_order
    ) AS previous_step_sessions,
    LEAD(sessions) OVER (
      PARTITION BY row_type, device_category
      ORDER BY step_order
    ) AS next_step_sessions,
    FIRST_VALUE(sessions) OVER (
      PARTITION BY row_type, device_category
      ORDER BY step_order
    ) AS entry_sessions
  FROM combined_step_counts
)
SELECT
  row_type,
  device_category,
  step_order,
  step_name,
  sessions,
  SAFE_DIVIDE(sessions, previous_step_sessions) AS conversion_from_previous_step,
  SAFE_DIVIDE(sessions, entry_sessions) AS conversion_from_entry,
  sessions - next_step_sessions AS drop_off_to_next_step
FROM with_comparisons
ORDER BY
  CASE row_type WHEN 'device' THEN 1 ELSE 2 END,
  device_category,
  step_order;

-- Result set 3: purchase-path coverage by assigned session device.
-- A purchase without a complete observed strict path is not abandonment.
WITH device_categories AS (
  SELECT DISTINCT device_category
  FROM session_device_assignment
),
purchase_sessions AS (
  SELECT DISTINCT
    user_pseudo_id,
    ga_session_id
  FROM valid_shopping_events
  WHERE event_name = 'purchase'
),
purchase_coverage_by_device AS (
  SELECT
    assignment.device_category,
    COUNT(*) AS sessions_with_purchase,
    COUNTIF(steps.purchase_ts IS NOT NULL) AS complete_strict_path_purchase_sessions,
    COUNTIF(steps.purchase_ts IS NULL) AS purchase_sessions_without_complete_observed_path
  FROM purchase_sessions AS purchase
  INNER JOIN session_device_assignment AS assignment
    USING (user_pseudo_id, ga_session_id)
  LEFT JOIN strict_session_steps AS steps
    USING (user_pseudo_id, ga_session_id, device_category)
  GROUP BY assignment.device_category
),
all_categories_with_coverage AS (
  SELECT
    categories.device_category,
    COALESCE(coverage.sessions_with_purchase, 0) AS sessions_with_purchase,
    COALESCE(
      coverage.complete_strict_path_purchase_sessions,
      0
    ) AS complete_strict_path_purchase_sessions,
    COALESCE(
      coverage.purchase_sessions_without_complete_observed_path,
      0
    ) AS purchase_sessions_without_complete_observed_path
  FROM device_categories AS categories
  LEFT JOIN purchase_coverage_by_device AS coverage
    USING (device_category)
),
purchase_coverage_output AS (
  SELECT
    'device' AS row_type,
    device_category,
    sessions_with_purchase,
    complete_strict_path_purchase_sessions,
    purchase_sessions_without_complete_observed_path
  FROM all_categories_with_coverage

  UNION ALL

  SELECT
    'all_devices',
    CAST(NULL AS STRING),
    SUM(sessions_with_purchase),
    SUM(complete_strict_path_purchase_sessions),
    SUM(purchase_sessions_without_complete_observed_path)
  FROM all_categories_with_coverage
)
SELECT
  row_type,
  device_category,
  sessions_with_purchase,
  complete_strict_path_purchase_sessions,
  purchase_sessions_without_complete_observed_path,
  SAFE_DIVIDE(
    complete_strict_path_purchase_sessions,
    sessions_with_purchase
  ) AS complete_strict_path_coverage
FROM purchase_coverage_output
ORDER BY
  CASE row_type WHEN 'device' THEN 1 ELSE 2 END,
  device_category;
