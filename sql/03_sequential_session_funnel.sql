-- RUN OUTPUTS RECORDED IN results/ FOR JANUARY 2021.
-- January 2021 sequential session funnel:
-- view_item -> add_to_cart -> begin_checkout -> purchase.
--
-- Counting unit: a valid (user_pseudo_id, ga_session_id) session.
-- Entry population: valid sessions containing view_item.
-- Main rule: every next step must have an event_timestamp strictly greater
-- than the selected prior step. Each step selects the earliest qualifying
-- event after that prior step, rather than independently selecting the first
-- event of each name in the session.
--
-- The script returns three result sets:
--   1. Main strict sequential funnel metrics.
--   2. Adjacent-step same-timestamp ambiguity diagnostics.
--   3. Purchase sessions without a complete observed strict path.
--
-- This is a session-level shopping path. It does not require the events in the
-- path to refer to the same item.

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

CREATE TEMP TABLE session_steps AS
WITH entry_sessions AS (
  SELECT
    user_pseudo_id,
    ga_session_id,
    MIN(event_timestamp) AS view_item_ts
  FROM valid_events
  WHERE event_name = 'view_item'
  GROUP BY
    user_pseudo_id,
    ga_session_id
),
add_to_cart_steps AS (
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

-- Result set 1: strict sequential funnel.
WITH step_counts AS (
  SELECT 1 AS step_order, 'view_item' AS step_name, COUNT(*) AS sessions
  FROM session_steps
  UNION ALL
  SELECT 2, 'add_to_cart', COUNTIF(add_to_cart_ts IS NOT NULL)
  FROM session_steps
  UNION ALL
  SELECT 3, 'begin_checkout', COUNTIF(begin_checkout_ts IS NOT NULL)
  FROM session_steps
  UNION ALL
  SELECT 4, 'purchase', COUNTIF(purchase_ts IS NOT NULL)
  FROM session_steps
),
with_comparisons AS (
  SELECT
    step_order,
    step_name,
    sessions,
    LAG(sessions) OVER (ORDER BY step_order) AS previous_step_sessions,
    LEAD(sessions) OVER (ORDER BY step_order) AS next_step_sessions,
    FIRST_VALUE(sessions) OVER (ORDER BY step_order) AS entry_sessions
  FROM step_counts
)
SELECT
  step_order,
  step_name,
  sessions,
  SAFE_DIVIDE(sessions, previous_step_sessions) AS conversion_from_previous_step,
  SAFE_DIVIDE(sessions, entry_sessions) AS conversion_from_entry,
  previous_step_sessions - sessions AS drop_off_from_previous_step,
  sessions - next_step_sessions AS drop_off_to_next_step
FROM with_comparisons
ORDER BY step_order;

-- Result set 2: timestamp ties are not admitted to the main funnel. The first
-- count reports sessions with a tied candidate at the transition; the second
-- reports sessions that did not advance strictly but did have such a tie.
WITH transitions AS (
  SELECT 1 AS transition_order, 'view_item -> add_to_cart' AS transition
  UNION ALL
  SELECT 2, 'add_to_cart -> begin_checkout'
  UNION ALL
  SELECT 3, 'begin_checkout -> purchase'
),
tie_candidates AS (
  SELECT
    1 AS transition_order,
    'view_item -> add_to_cart' AS transition,
    steps.add_to_cart_ts AS strict_next_step_ts,
    steps.user_pseudo_id,
    steps.ga_session_id
  FROM session_steps AS steps
  INNER JOIN valid_events AS events
    ON steps.user_pseudo_id = events.user_pseudo_id
    AND steps.ga_session_id = events.ga_session_id
    AND events.event_name = 'add_to_cart'
    AND events.event_timestamp = steps.view_item_ts

  UNION ALL

  SELECT
    2,
    'add_to_cart -> begin_checkout',
    steps.begin_checkout_ts,
    steps.user_pseudo_id,
    steps.ga_session_id
  FROM session_steps AS steps
  INNER JOIN valid_events AS events
    ON steps.user_pseudo_id = events.user_pseudo_id
    AND steps.ga_session_id = events.ga_session_id
    AND steps.add_to_cart_ts IS NOT NULL
    AND events.event_name = 'begin_checkout'
    AND events.event_timestamp = steps.add_to_cart_ts

  UNION ALL

  SELECT
    3,
    'begin_checkout -> purchase',
    steps.purchase_ts,
    steps.user_pseudo_id,
    steps.ga_session_id
  FROM session_steps AS steps
  INNER JOIN valid_events AS events
    ON steps.user_pseudo_id = events.user_pseudo_id
    AND steps.ga_session_id = events.ga_session_id
    AND steps.begin_checkout_ts IS NOT NULL
    AND events.event_name = 'purchase'
    AND events.event_timestamp = steps.begin_checkout_ts
),
tied_sessions AS (
  SELECT
    transition_order,
    transition,
    user_pseudo_id,
    ga_session_id,
    strict_next_step_ts IS NULL AS blocked_strictly
  FROM tie_candidates
  GROUP BY
    transition_order,
    transition,
    user_pseudo_id,
    ga_session_id,
    blocked_strictly
)
SELECT
  transitions.transition_order,
  transitions.transition,
  COUNT(tied.user_pseudo_id) AS sessions_with_tied_candidate,
  COUNTIF(tied.blocked_strictly) AS sessions_blocked_strictly_with_tied_candidate
FROM transitions
LEFT JOIN tied_sessions AS tied
  USING (transition_order, transition)
GROUP BY
  transitions.transition_order,
  transitions.transition
ORDER BY transitions.transition_order;

-- Result set 3: purchase sessions outside the complete observed strict path
-- remain a separate diagnostic and are not added to the funnel purchase step.
WITH purchase_sessions AS (
  SELECT DISTINCT
    user_pseudo_id,
    ga_session_id
  FROM valid_events
  WHERE event_name = 'purchase'
),
complete_path_sessions AS (
  SELECT
    user_pseudo_id,
    ga_session_id
  FROM session_steps
  WHERE purchase_ts IS NOT NULL
)
SELECT
  COUNT(*) AS sessions_with_purchase,
  COUNTIF(complete.user_pseudo_id IS NOT NULL) AS sessions_with_complete_observed_path,
  COUNTIF(complete.user_pseudo_id IS NULL) AS purchase_sessions_without_complete_observed_path
FROM purchase_sessions AS purchase
LEFT JOIN complete_path_sessions AS complete
  USING (user_pseudo_id, ga_session_id);
