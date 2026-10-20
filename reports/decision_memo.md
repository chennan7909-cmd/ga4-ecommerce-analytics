# Ecommerce Path Decision Memo

## 1. Business question

Where does the observed ecommerce path show the largest opportunity for further investigation, and what should the product team do before considering a product change? This memo summarizes recorded aggregate results from the Google Merchandise Store GA4 obfuscated sample for January 1–31, 2021. It is intended to guide the next decision, not to estimate the performance of another business or claim that any interface element causes the observed pattern.

The analysis covers 23,191 valid sessions containing at least one of six defined shopping events. The primary funnel is narrower: it begins with the 23,105 valid sessions containing `view_item` and requires `view_item → add_to_cart → begin_checkout → purchase` in strict timestamp order. All figures below are recalculated from the aggregate CSV files in `results/`.

## 2. Key findings

The strict sequential session funnel is **23,105 → 4,223 → 1,455 → 811**. Thus, 811 sessions completed the full observed path, or **3.5101% of the 23,105 entry sessions**. The largest observed step gap is between product view and add to cart: 4,223 sessions reached add to cart after a qualifying view, equal to 18.2774% of entry sessions. This gap is also the largest in absolute session count for desktop, mobile, and tablet.

Timestamp sensitivity is small at the final step but relevant to interpretation. Allowing a later step at the same timestamp (`>=`) produces an observed complete-path rate of **3.5923%**, compared with 3.5101% under the primary strict (`>`) rule: a difference of **0.0822 percentage points**. This relaxed result is a sensitivity check only. Equal timestamps do not establish the events' true order.

Device results are descriptive. Desktop has 446 complete strict paths among 13,438 entry sessions, approximately **3.32%**. Mobile has 344 among 9,111, approximately **3.78%**. Tablet has 21 among 556, also approximately **3.78%**, but its entry sample is much smaller. These figures do not establish statistically significant differences and do not identify mobile as a problem device.

Purchase-path coverage provides a separate reconciliation. There are **1,115 valid sessions containing purchase**: 811 have the complete strict four-step observed path and 304 do not. The 304 sessions are purchases with an incomplete observed path under this definition; they are not abandoned carts.

## 3. Recommended actions

First, verify instrumentation and path coverage at the product-view-to-add-to-cart transition. Confirm that relevant product pages fire the expected events consistently, that duplicate or delayed events are understood, and that event timestamps have sufficient resolution. Review whether consent, client-side failures, navigation behavior, or page variants could selectively suppress either event. Reconcile the event design with actual page flows before treating the observed gap as a product-behavior problem.

Second, investigate product-detail-page decision barriers across all eligible devices. Conduct a structured page assessment and, if necessary, targeted user research. Potential questions include whether delivery timing, returns, variant selection, stock status, or other decision-critical information is clear at the point of action. The observed data do not prove that the add-to-cart control or page design is defective, so investigation should precede intervention.

Third, retain device as a diagnostic and pre-specified exploratory dimension rather than targeting mobile by default. Any prioritization should also consider traffic volume, technical issues, user context, and uncertainty around the smaller tablet sample.

## 4. Proposed experiment

After instrumentation checks, page evaluation, and any necessary user research, consider whether a concise delivery-and-returns summary near the existing add-to-cart area is an appropriate candidate. The proposed test would compare the current page with a version that adds only this summary while holding price, promotion, and checkout flow constant. It would use stable user-level 50/50 assignment and a pre-defined seven-day outcome window, subject to confirmation against the business decision cycle.

The primary metric would be the proportion of enrolled users with at least one add-to-cart event in that window. It is deliberately not the current 18.2774% session-level view-to-cart rate, because the experimental metric has a different unit and eligibility definition. Details on eligibility, intent-to-treat analysis, guardrails, data quality, and sample-size planning are in the [Product Detail Page Add-to-Cart Experiment Proposal](../docs/ab_test_proposal.md). **Status: Proposal only — not executed.** No randomized assignment or experiment-effect result exists in this dataset.

## 5. Limitations

The source is an obfuscated Google Merchandise Store sample limited to January 2021. The funnel is session-level and can connect steps across different products; it is not a same-SKU path. Month boundaries, purchases occurring in another session, missing or delayed events, and strict timestamp ordering can all affect observed completeness. A missing next step is not proof of real user loss, and the 304 purchase sessions without a complete observed strict path are not abandonment.

Device comparisons are observational and neither prove statistical significance nor a causal device effect. The 3.5101% complete-path rate is not a site-wide purchase conversion rate. Finally, these sample rates cannot be used to forecast revenue, experiment lift, or returns for a real enterprise. A production decision requires current first-party data, a metric-matched baseline, expected eligible-user volume, operational guardrails, and a business-selected minimum worthwhile effect.
