# Resume evidence

## Verified project work

- Designed an A/B test proposal with user-level randomization, predefined
  success metrics, guardrails, and a sample-size planning framework.

## Claim boundary

Only the design work above is supported. No randomized experiment outcome is
available in this project.

## Predictive extension (implementation, not measured business performance)

- Implemented fixed-landmark session feature construction with future-purchase labels,
  censoring rules, purged temporal splits, Logistic Regression and LightGBM evaluation.
- Added held-out SHAP explanations and aggregate device/probability-band summaries.
- Implemented LLM SQL generation and report orchestration over restricted local copies
  of recorded aggregate results, with AST checks and read-only execution controls.
- Added a SQL metric benchmark and synthetic end-to-end model tests.

Real-event training, real PR metrics, live LLM SQL accuracy, narrative reliability,
high-value customer identification, causal effects, and deployed platform usage have
not been established. Do not describe the source session count as the model sample size.
See predictive_platform.md for execution and evaluation instructions.
