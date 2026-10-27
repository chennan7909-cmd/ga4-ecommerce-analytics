# Resume evidence

## Verified project work

- Designed an A/B test proposal with user-level randomization, predefined
  success metrics, guardrails, and a sample-size planning framework.

## Claim boundary

Only the design work above is supported. No randomized experiment outcome is
available in this project.

## Predictive extension (implementation, not measured business performance)

- Implemented fixed-landmark session feature construction with future-purchase labels,
  exact-duplicate reporting, censoring rules, purged temporal splits, train-only
  preprocessing, validation-only thresholds, and baseline/Logistic/LightGBM evaluation.
- Added held-out calibration, ranking and error metrics, SHAP association explanations,
  representative-sample detail, aggregate device/probability-band summaries, and charts.
- Implemented LLM SQL generation and report orchestration over restricted local copies
  of recorded aggregate results, with AST checks, read-only execution, query budgets,
  evidence retention, and explicit refusal/failure states.
- Added a dry-run-first BigQuery event export path, event data contract, aggregate
  integrity checks, a 15-case SQL/refusal benchmark, and synthetic end-to-end model tests.

Verified locally: 28 tests, original chart regeneration, 15/15 offline gold SQL cases,
and 15/15 deterministic simulated-generation cases. The simulated mode is not a real
LLM call. Real-event training, real prediction metrics, live LLM SQL accuracy, narrative reliability,
high-value customer identification, causal effects, and deployed platform usage have
not been established. Do not describe the source session count as the model sample size.
See predictive_platform.md for execution and evaluation instructions.
