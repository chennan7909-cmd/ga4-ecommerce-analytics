# Metric definitions

These definitions prevent event coverage from being mistaken for a sequential
conversion funnel. Unless a query says otherwise, the current scope is the six
e-commerce events in January 2021.

## Event count

`event_count` is the number of GA4 export rows whose `event_name` equals the
named event. Each exported row contributes one, including repeated events from
the same user or session.

## Distinct users

`users` is `COUNT(DISTINCT user_pseudo_id)` within each event. BigQuery excludes
`NULL` from this count. A user can appear in more than one event row, so user
counts cannot be added across events.

## Sessions

`ga_session_id` is read from `event_params`. It is not treated as globally
unique. A valid session requires both a non-`NULL` `user_pseudo_id` and a
non-`NULL` `ga_session_id`, and is identified by their distinct pair:
`(user_pseudo_id, ga_session_id)`.

Events without either part of that key are excluded from session-based metrics
and reported separately by the data-quality query.

For the six January 2021 shopping events, the recorded data-quality result has
121,524 event rows and 23,191 valid sessions. Both `user_pseudo_id` and
`ga_session_id` have 0 missing rows (0.0%), so all 121,524 rows have a valid
session key in this recorded scope.

## Sequential funnel

A sequential funnel counts users or valid sessions that reach defined steps in
the required order. It must specify:

- the counting unit (user or valid session);
- the step order and how repeated events are handled;
- the timestamp/order rule and analysis window;
- whether each later step must follow all preceding steps;
- the denominator used for each conversion rate.

The event coverage CSV contains independent counts by event. Ratios between its
rows are **not** sequential funnel conversion rates, because the CSV does not
establish that the same user or session completed those events in order.

The January 2021 strict funnel uses valid sessions containing `view_item` as its
entry population and follows `view_item` -> `add_to_cart` ->
`begin_checkout` -> `purchase`. Each step is counted at most once per session.
For every later step, the query selects the earliest qualifying event strictly
after the timestamp chosen for the preceding step. Events at the same timestamp
do not establish order and are reported separately as diagnostics.

Funnel conversion rates are defined as:

- adjacent-step conversion: current-step sessions divided by previous-step
  sessions;
- entry conversion: current-step sessions divided by `view_item` entry
  sessions;
- observed-path drop-off from the previous step: previous-step sessions minus
  current-step sessions;
- observed-path drop-off to the next step: current-step sessions minus next-step
  sessions.

The entry step has no adjacent conversion or drop-off from a previous step, and
the final step has no drop-off to a next step; those output cells are `NULL`.

These differences describe what was not observed at the next qualifying step in
the selected data and ordering rule. They must not be interpreted as confirmed
user abandonment or real-world loss.

Sessions containing `purchase` without the complete observed strict path are
reported separately and are not forced into the completed funnel. They are not
cart-abandonment sessions because a purchase is present. This is a session-level
shopping path; it does not require all steps to concern the same item.

## Timestamp sensitivity

The strict `event_timestamp > prior_step_timestamp` funnel remains the primary
metric. The sensitivity query also calculates a relaxed
`event_timestamp >= prior_step_timestamp` path and compares session counts and
conversion rates at every step.

The relaxed path is only a permissive comparison. Equal timestamps do not prove
the real order of events, so its results must not replace the strict primary
metric or be described as confirmed ordered behavior.

The recorded strict path is 23,105 -> 4,223 -> 1,455 -> 811 sessions. The
recorded relaxed path is 23,105 -> 4,529 -> 1,533 -> 830 sessions, a difference
of 0, 306, 78, and 19 sessions by step. The strict columns exactly reproduce the
primary funnel.

Complete observed path conversion is 3.5101% under `>` and 3.5923% under `>=`,
a difference of 0.0822 percentage points. This difference measures sensitivity
to the timestamp rule; it does not resolve the true order of tied events.

Neither result is a site-wide purchase conversion rate. The denominator is the
valid-session `view_item` entry population in the selected event scope. The path
also does not require the same item across steps.

## Device assignment and grouped metrics

Device assignment is defined once per valid shopping session using the six
shopping events in the January 2021 window:

- exactly one distinct nonempty `device.category`: assign that category;
- no nonempty category: assign `unknown`;
- more than one distinct nonempty category: assign `mixed`.

No device category is filtered, and each session belongs to exactly one output
group. The grouped strict funnel then counts each session at most once per step.
Rows with `row_type = 'device'` are device-specific; the `all_devices` row is a
sum across the mutually exclusive device assignments for reconciliation.

In the device-assignment quality output:

- `valid_shopping_sessions` is a session count;
- `valid_shopping_event_rows` and `missing_device_category_event_rows` are event-row
  counts;
- `sessions_with_missing_device_category` counts sessions with at least one
  blank or missing device-category event row;
- `sessions_with_multiple_nonempty_device_categories` counts sessions with more
  than one distinct observed nonempty category.

For each device and step:

- `sessions` is the number of assigned sessions reaching that strict step;
- `conversion_from_previous_step` divides by the preceding step's sessions in
  the same device group;
- `conversion_from_entry` divides by that device group's `view_item` sessions;
- `drop_off_to_next_step` subtracts the next strict step from the current step.

`SAFE_DIVIDE` preserves `NULL` when a denominator is zero. “Drop-off” remains an
observed-path difference, not confirmed user abandonment.

In purchase-path coverage, `sessions_with_purchase` is the denominator and
`complete_strict_path_purchase_sessions` is the numerator. Therefore
`complete_strict_path_coverage` is `NULL` for a device with no purchase session.
Purchase sessions without a complete observed path are a coverage category, not
abandonment.

Device assignment is limited to device values present on the six scoped shopping
events. `unknown` means no nonempty category was observed on those rows, not that
the real device was unknowable; `mixed` indicates inconsistent or changing
categories within the observed session rows, not a chosen dominant device.
Values on other events or outside the January window are not consulted.

The recorded device outputs contain desktop, mobile, and tablet assignments. No
missing device-category event rows or multi-category sessions were recorded in
this scope. Their `all_devices` rows reproduce the previously recorded global
session, funnel, and purchase-path totals. These descriptive results do not
establish a causal device effect.

## Recorded event coverage

The following values are transcribed from
`results/event_coverage_2021-01.csv`; no missing session or sequential-funnel
result is inferred from them.

| event_name | event_count | users |
|---|---:|---:|
| `view_item` | 86,971 | 19,629 |
| `add_to_cart` | 15,522 | 3,832 |
| `begin_checkout` | 11,034 | 1,924 |
| `add_shipping_info` | 3,952 | 1,924 |
| `add_payment_info` | 2,841 | 1,395 |
| `purchase` | 1,204 | 1,069 |

## Recorded identity and session-key quality

The following values are transcribed from
`results/user_session_quality_2021-01.csv` for the same six shopping events.

| Metric | Recorded value |
|---|---:|
| Event rows | 121,524 |
| Missing `user_pseudo_id` rows | 0 (0.0%) |
| Missing `ga_session_id` rows | 0 (0.0%) |
| Invalid session-key rows | 0 (0.0%) |
| Valid-session event rows | 121,524 |
| Valid sessions | 23,191 |

## Recorded strict sequential session funnel

The following values are transcribed from
`results/sequential_session_funnel_2021-01.csv` and arithmetically checked.

| Step | Sessions | From previous | From entry | Drop-off from previous | Drop-off to next |
|---|---:|---:|---:|---:|---:|
| `view_item` | 23,105 | — | 100.0000% | — | 18,882 |
| `add_to_cart` | 4,223 | 18.2774% | 18.2774% | 18,882 | 2,768 |
| `begin_checkout` | 1,455 | 34.4542% | 6.2973% | 2,768 | 644 |
| `purchase` | 811 | 55.7388% | 3.5101% | 644 | — |

The entry population is smaller than the 23,191 valid sessions containing any
of the six shopping events because the funnel specifically requires
`view_item`; 23,105 qualifying entry sessions were observed.

## Recorded timestamp-tie diagnostics

| Transition | Sessions with tied candidate | Strictly blocked sessions with tied candidate |
|---|---:|---:|
| `view_item -> add_to_cart` | 720 | 306 |
| `add_to_cart -> begin_checkout` | 0 | 0 |
| `begin_checkout -> purchase` | 0 | 0 |

These diagnostics identify timestamp ambiguity. They do not establish which
event really occurred first.

## Recorded purchase-path reconciliation

| Classification | Sessions |
|---|---:|
| Complete observed strict path | 811 |
| Purchase without complete observed strict path | 304 |
| All sessions containing `purchase` | 1,115 |

The recorded counts reconcile because `811 + 304 = 1,115`. The 304 sessions
must not be called abandonment: a purchase is present, while the complete path
was not observed under the current scope and strict ordering rule.

The event coverage result separately records 1,204 `purchase` event rows. That
does not conflict with 1,115 purchase sessions: event rows and distinct sessions
are different units, and one session may contain multiple purchase event rows.

## Recorded timestamp sensitivity

The following values are transcribed from
`results/timestamp_sensitivity_2021-01.csv` and recalculated from its session
counts.

| Step | Strict | Relaxed | Difference | Strict adjacent | Relaxed adjacent | Strict entry | Relaxed entry |
|---|---:|---:|---:|---:|---:|---:|---:|
| `view_item` | 23,105 | 23,105 | 0 | — | — | 100.0000% | 100.0000% |
| `add_to_cart` | 4,223 | 4,529 | 306 | 18.2774% | 19.6018% | 18.2774% | 19.6018% |
| `begin_checkout` | 1,455 | 1,533 | 78 | 34.4542% | 33.8485% | 6.2973% | 6.6349% |
| `purchase` | 811 | 830 | 19 | 55.7388% | 54.1422% | 3.5101% | 3.5923% |

## Recorded device-grouped strict funnel

The following values are transcribed from
`results/device_session_funnel_2021-01.csv`.

| Device | View-item sessions | Add-to-cart sessions | Begin-checkout sessions | Purchase-path sessions | Purchase path / entry |
|---|---:|---:|---:|---:|---:|
| Desktop | 13,438 | 2,438 | 834 | 446 | 3.3189% |
| Mobile | 9,111 | 1,692 | 584 | 344 | 3.7757% |
| Tablet | 556 | 93 | 37 | 21 | 3.7770% |
| All devices | 23,105 | 4,223 | 1,455 | 811 | 3.5101% |

For desktop, mobile, and tablet, the largest absolute observed-path difference
is `view_item -> add_to_cart`. This common pattern identifies an investigation
area; it does not identify the cause, prove a page defect, or single out mobile
as the problem device.

The device purchase-path output reconciles to 1,115 sessions with `purchase`:
811 have a complete observed strict path and 304 do not. As elsewhere, an
unobserved full path is not abandonment.
