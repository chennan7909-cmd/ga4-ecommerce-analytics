# Product Detail Page Add-to-Cart Experiment Proposal

**Status: Proposal only — not executed.**

This document turns an observational funnel finding into a testable experiment
design. The experiment has not been implemented, and there is no randomized
assignment data or experimental effect estimate. Google's obfuscated public GA4
sample is useful for exploring questions and demonstrating an analysis method;
it cannot validate the effect of the proposed product change.

## 1. Observational context

The January 2021 analysis uses valid GA4 sessions identified by
`(user_pseudo_id, ga_session_id)`. Its primary funnel requires strictly
increasing timestamps for `view_item -> add_to_cart -> begin_checkout ->
purchase`. It is a session-level observed path, not a same-item funnel or a
site-wide purchase conversion rate.

Recorded results relevant to this proposal are:

| Evidence | Recorded result |
|---|---:|
| Strict-funnel entry sessions | 23,105 |
| Complete strict purchase paths | 811 |
| Complete strict path / entry sessions | 3.5101% |
| Relaxed `>=` sensitivity result | 3.5923% |
| Mobile complete strict path / mobile entry sessions | 344 / 9,111 = 3.7757% |
| Desktop complete strict path / desktop entry sessions | 446 / 13,438 = 3.3189% |

For every recorded device category—desktop, mobile, and tablet—the largest
absolute observed-path gap is between `view_item` and `add_to_cart`:

| Device | View-item sessions | Add-to-cart sessions | Observed-path difference |
|---|---:|---:|---:|
| Desktop | 13,438 | 2,438 | 11,000 |
| Mobile | 9,111 | 1,692 | 7,419 |
| Tablet | 556 | 93 | 463 |

These results support further investigation of the product-detail-page to
add-to-cart decision point. They do **not** show that the current button or page
design is defective, identify why later events were not observed, or establish
that mobile is the problem device. Mobile's recorded complete-path rate is not
lower than desktop's, and neither comparison is causal.

Before an experiment, the team should audit instrumentation, review the actual
page and content hierarchy, and conduct user research if needed. The candidate
intervention below should be changed or abandoned if that work shows it is
irrelevant, already present, technically infeasible, or likely to confuse users.

## 2. Candidate intervention and hypothesis

### Candidate intervention

Add a concise delivery-and-returns information summary to the existing
add-to-cart decision area on eligible product detail pages.

This is a product hypothesis, not a claim that the current page lacks delivery
or returns information. No current-page screenshot, usability finding, or user
complaint is available from the public sample.

### Hypothesis

Presenting clear delivery and returns information near the purchase decision
may reduce uncertainty and increase the proportion of eligible users who add at
least one item to cart.

### Variants

- **Control (A):** current product detail page.
- **Treatment (B):** current page plus the concise delivery-and-returns summary
  in the existing add-to-cart area.

Price, promotions, product availability logic, add-to-cart behavior, and the
checkout flow should remain unchanged. The experiment should include all
eligible devices; it is not designed as a mobile-only treatment.

## 3. Population, assignment, and eligibility

Use stable user-level randomization with a planned 50/50 allocation.

- The same identifiable user must remain in the same variant throughout the
  experiment.
- Define eligible product pages, geography or market restrictions, employee and
  bot exclusions, and other user exclusions before launch.
- Define enrollment at the user's first eligible product-detail-page event.
- Determine eligibility and write the assignment record before treatment is
  shown. Do not define the analysis population using post-treatment behavior.
- Analyze assigned users by intention to treat (ITT), regardless of whether the
  exposure event was successfully recorded.
- Use exposure logs to diagnose delivery quality, but do not change the primary
  population to only users with a successful exposure record.

Anonymous identifier resets can assign the same person more than once. A user
who switches devices may receive different assignments unless a reliable
cross-device account identifier is available. Shared devices, cookie deletion,
cross-device use, and users seeing or sharing content across variants can also
create contamination. These limitations should be measured where possible and
reported with the results.

## 4. Metrics

### Primary metric

The primary metric is the proportion of enrolled users who record at least one
`add_to_cart` event during a fixed seven-day window beginning at first eligible
enrollment. Seven days is a design assumption and must be confirmed against the
business's normal decision cycle before launch.

Each enrolled user contributes one binary outcome:

- `1` if at least one qualifying add-to-cart occurs in the observation window;
- `0` otherwise, assuming outcome logging and window completeness pass quality
  checks.

The existing 18.28% strict session-level `view_item -> add_to_cart` rate is not
a baseline for this user-level metric. It uses a different unit, eligibility
definition, and observation window.

### Secondary metrics

- User-level purchase rate within the same observation window.
- Revenue per enrolled user, only if transaction deduplication, amount fields,
  refunds, and currency conversion are reliable.
- Pre-specified device results as exploratory subgroup analysis, not as separate
  primary tests or evidence that one device was the original problem.

### Guardrails

- Product-page performance, using a pre-defined technical measure such as an
  agreed page-load or Core Web Vitals metric.
- Add-to-cart error rate.
- User-level purchase-rate deterioration.

Statistical guardrail tests and operational stopping thresholds are different.
The existing public sample cannot set acceptable latency, error, or purchase
degradation thresholds. Product, engineering, analytics, and business owners
must approve those thresholds before launch, including who can pause the test
and what evidence is required.

## 5. Future experiment data contract

The production experiment should record, at minimum:

| Record | Required fields |
|---|---|
| Assignment | `experiment_id`, `variant`, stable user identifier, `assignment_timestamp`, eligibility record and rule version |
| Exposure | `experiment_id`, `variant`, user identifier, exposure timestamp, page or product context, device |
| Outcomes | user identifier, event name, event timestamp, device, and enough context to apply the pre-defined outcome rules |
| Purchase | reliable `transaction_id`, purchase timestamp, and user identifier |
| Revenue, if used | deduplicated transaction amount, currency, refund treatment, and validated conversion logic |

These are proposed requirements for a future experiment. The public GA4 sample
does not contain randomized experiment assignment fields for this proposal.

Required pre-analysis quality checks include:

- sample-ratio mismatch (SRM) against the planned allocation;
- users appearing in both variants;
- missing, delayed, duplicated, or contradictory assignment and exposure logs;
- duplicate outcome events and purchase deduplication by reliable
  `transaction_id`;
- complete seven-day outcome windows for included enrollment cohorts;
- evidence that eligibility or enrollment was not conditioned on
  treatment-affected behavior;
- assignment, exposure, and outcome timestamps in a valid order;
- comparable instrumentation coverage by variant and device.

Failure of a material quality check should block effect interpretation until the
cause and impact are understood.

## 6. Statistical analysis plan

The primary analysis compares user-level binary outcome proportions under ITT.
Report:

- the control and treatment proportions;
- the absolute difference in percentage points;
- the relative lift when the control proportion is nonzero;
- a 95% confidence interval for the absolute difference.

Pre-specify a two-sided test with alpha 0.05 and 80% power. Use one primary
metric. Secondary metrics and device subgroups should be reported completely and
identified as secondary or exploratory; multiplicity and selective-reporting
risk must be considered when interpreting them.

Do not stop because a daily p-value first crosses a threshold. Monitor only the
pre-approved operational and data-quality conditions during the run. After
enrollment closes, allow the final enrolled cohort to complete the full
seven-day outcome window before the primary analysis.

## 7. Sample-size and duration planning

No current result supplies both a matching user-level baseline and the daily
number of independent eligible users. Therefore this proposal does not claim a
determined sample size or runtime, and it does not convert the 23,105 strict
entry sessions into independent users.

Before launch:

1. Measure the primary metric's control-style baseline using the exact planned
   user eligibility, enrollment, event, deduplication, and seven-day window
   definitions.
2. Estimate daily independent eligible users after exclusions and expected
   identity loss.
3. Choose the minimum detectable effect (MDE) in absolute percentage points
   based on business value and implementation cost—not on what is easiest to
   detect.
4. Calculate equal-allocation sample size per arm for two independent
   proportions using the measured baseline, MDE, two-sided alpha 0.05, and 80%
   power. Record the method, software version, and input assumptions.
5. Set duration to satisfy the sample requirement, cover complete weekly
   cycles, and leave seven days for the final cohort's outcomes to mature.

Any scenario calculation shown before these inputs are available must be
prominently labelled hypothetical and must not be presented as the actual
baseline, committed sample size, or expected lift.

## 8. Decision rules

1. **Quality passes, primary metric improves, and guardrails are acceptable:**
   assess practical value and consider a monitored gradual rollout.
2. **The result is uncertain:** report the confidence interval and the range of
   effects the experiment can reasonably exclude. Do not translate
   non-significance into “no effect.”
3. **A guardrail worsens or data quality fails:** pause the decision and
   investigate before interpreting or launching the treatment.

Statistical significance on the primary metric is not sufficient by itself.
The decision must also consider effect size, purchase outcomes, guardrails,
implementation and maintenance cost, and operational risk. This proposal makes
no guaranteed lift or revenue claim.

## 9. Interpretation boundaries

- The source analysis is observational and cannot identify causal drivers.
- The public sample is obfuscated and limited to the January 2021 query window.
- Session paths may be incomplete at observation boundaries.
- Missing observed events do not necessarily represent real user abandonment.
- The funnel does not require all events to refer to the same item.
- The relaxed timestamp analysis cannot determine the true order of tied events.
- Device differences are descriptive and do not justify targeting or excluding
  a device without further evidence.

The proposal should be updated after instrumentation review, page evaluation,
user research, baseline measurement, MDE selection, and operational threshold
approval.
