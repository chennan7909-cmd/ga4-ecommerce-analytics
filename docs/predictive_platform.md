# GA4 conversion prediction and LLM analysis

## Implementation and evidence status

The repository contains executable event validation, landmark feature construction,
purged temporal model evaluation, SHAP explanation, probability-band summaries, a
restricted LLM SQL analysis command, and separate offline, simulated, and live
SQL-generation evaluation modes. It is a command-line research prototype, not a
deployed service. There is no production inference endpoint or saved model service.

Real GA4 model training has **not** been executed: the repository contains aggregate CSV
results, not the required event-level export. No real GA4 prediction performance, SHAP
business finding, high-value customer identification, or intervention lift is claimed.
Model plumbing is tested with explicitly synthetic fixtures only. No live LLM API was
called because the required configuration was unavailable.

The latest local verification completed 28 tests, a 15-case offline gold SQL regression,
and a 15-case deterministic simulated-LLM regression. The simulated adapter returns
fixtures and is explicitly not a real model call. Offline gold SQL verifies analytics
logic, not SQL-generation capability.

## Install

Python 3.11 or 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
```

Matplotlib is included in the model dependencies. The original chart requirements remain
in `requirements.txt`. Tests and offline evaluations require no credentials.

## Event export and target

Use the dry-run-first wrapper with your own billing project. It reads
`sql/06_prediction_events.sql`, enforces a maximum-bytes-billed limit, and executes only
when `--execute` is explicitly supplied. The query retains the same six shopping events
as the original descriptive analysis. Do not commit event identities. See the
[prediction data contract](prediction_data_contract.md) for the schema, duplicate policy,
integrity checks, and evidence boundary.

```bash
pip install -e '.[bigquery]'
python scripts/export_prediction_events.py \
  --project YOUR_BILLING_PROJECT \
  --max-bytes-billed 5000000000

# Review the dry-run estimate, then run the export explicitly.
python scripts/export_prediction_events.py \
  --project YOUR_BILLING_PROJECT \
  --max-bytes-billed 5000000000 \
  --execute

python -m ga4_platform.cli validate-data \
  --events data/raw/events.csv \
  --observation-end 2021-02-01T00:00:00Z

python -m ga4_platform.cli features \
  --events data/raw/events.csv \
  --observation-end 2021-02-01T00:00:00Z

python -m ga4_platform.cli train \
  --features data/processed/features.csv \
  --data-source "BigQuery public GA4 event export, 2021-01"
```

One example represents one `(user_pseudo_id, ga_session_id)` session. The prediction
landmark is 60 seconds after the first `view_item`. The label is any same-session
`purchase` strictly after the landmark and at or before the following 24-hour endpoint.
Buyers at or before the landmark are excluded. Because source data end at an exclusive
boundary while the label endpoint is inclusive, `label_end` must be strictly earlier
than `observation_end`; otherwise the example is right-censored and excluded.

Features use only events from the first view through the landmark, inclusive. Purchase is
never a feature. Counts cover the five non-purchase shopping events, plus observed-event
count, active seconds, mean gap between distinct timestamps, unambiguous event-type
transitions, and device at the first-view timestamp. Equal-timestamp mixed event groups
do not receive an invented sequence order. No full-session duration, future checkout,
purchase amount, identity, or purchase-event count enters the model.

Validation removes and reports only exact duplicate rows across the complete exported
contract. Repeated events with a differing exported field remain. Events are grouped
across dates within the same session when present in the export. Missing device becomes
`unknown`; multiple nonblank first-view categories become `mixed`.

The target does not capture cross-session conversion or lifetime value. It cannot
identify genuine abandonment, and a purchase event is not necessarily a deduplicated
commercial transaction. The caller must guarantee complete source partitions; code can
reject rows outside a declared boundary but cannot prove an upstream partition is absent.

The model population is a subset of the recorded 23,191 valid shopping sessions and must
be recounted after export, duplicate handling, landmarking, censoring, and exclusion.
The original 121,524 event rows and 23,191 sessions remain descriptive source-scope
figures, not model sample sizes.

## Temporal evaluation and models

Chronological 60/20/20 boundaries are purged so training labels end before validation
predictions begin and validation labels end before test predictions begin. Preprocessing
is fit only on training data. Each split must contain both target classes. The report
records sessions, positives, positive rate, prediction and label date ranges, distinct
users, repeated-user session counts, pairwise user overlap, purged rows, and data source.
This evaluates future sessions, not unseen-user generalization.

The comparison includes a training-prevalence constant baseline, Logistic Regression,
and LightGBM. Fixed hyperparameters avoid tuning on test. Each learned model selects its
F1 threshold on validation only, using precision and then the higher threshold as
deterministic tie breaks. Test labels never determine a threshold.

Reported metrics are Average Precision, trapezoidal PR-AUC, Precision, Recall, F1,
Brier Score, ten-bin expected calibration error and bin details, Precision@Top10%, and
Lift@Top10%. Average Precision is a ranking-weighted step summary; trapezoidal PR-AUC
interpolates the precision-recall curve. They are related but not interchangeable.
Top-k rounds up; probability ties use stable chronological order and may affect small
samples. Predictive lift is not causal intervention lift.

`artifacts/model/` contains:

- `metrics.json` with population, split, overlap, threshold, and metric details;
- `test_predictions.csv` with row ordinals, labels, and probabilities but no identities;
- `shap_global.csv` and `shap_global.png`;
- `shap_example.csv` for the held-out row closest to the median LightGBM probability;
- `segments.csv` and `segments.png` for device/probability-band summaries;
- `model_comparison.png` and `calibration.png`.

At most 500 held-out rows contribute to SHAP. SHAP values describe LightGBM raw log-odds
associations, not causal effects or customer value. Low/medium/high probability bands use
fixed boundaries of 0.1 and 0.5 and are illustrative, not validated campaign thresholds.
“Higher purchase propensity” must not be restated as “higher customer value.”

## LLM SQL analysis

The source warehouse is BigQuery. The assistant does **not** run generated SQL against
BigQuery. It queries an in-memory SQLite copy of approved aggregate result CSVs and,
optionally, a held-out model segment aggregate. This boundary prevents raw event
identities from being sent to the LLM provider.

```bash
export OPENAI_API_KEY='...'
export OPENAI_MODEL='ACCOUNT_AVAILABLE_MODEL'
python -m ga4_platform.cli ask \
  'Which device has the lowest strict complete-path rate?'
python -m ga4_platform.cli ask \
  --segments artifacts/model/segments.csv \
  'Compare observed purchase rates across model probability bands.'
```

Flow: business question → LLM SQL JSON → AST validation → read-only SQLite execution →
evidence package → LLM narrative. The orchestration uses two explicit API calls; it is
not a native function-calling agent. A fixed test double is used only when `--simulate`
is requested and is never described as a live LLM.

Only approved tables and scalar functions are allowed. Multiple statements, CTEs,
schema-qualified access, writes, commands, and unapproved functions are rejected.
SQLite `query_only`, an authorizer, VM-step and elapsed-time budgets, and a 200-row cap
provide layered controls. Required aggregate files are checked before loading.

The authoritative answer package retains the question, SQL, returned columns and rows,
metric context, source, and limitations. Unsupported questions return a refusal. Invalid
SQL, unavailable tables, permissions, resource exhaustion, or provider failures return a
failure state without invented evidence. If only the narrative call fails, SQL evidence
is retained and the narrative is marked unavailable. Generated prose always requires
review and must not invent revenue, lifetime value, causal effects, or experiment lift.

## Dual evaluation

```bash
# Gold SQL and expected aggregates; no LLM call.
python -m ga4_platform.cli evaluate-agent \
  --output artifacts/agent_offline_evaluation.json

# Deterministic fixture responses; explicitly NOT a real LLM call.
python -m ga4_platform.cli evaluate-agent --simulate \
  --output artifacts/agent_simulated_evaluation.json

# Actual SQL generation; requires credentials and incurs provider usage.
python -m ga4_platform.cli evaluate-agent --live \
  --output artifacts/agent_live_evaluation.json
```

The 15-case set contains ten executable questions and five expected refusals. It covers
source scope, denominator errors, strict paths versus purchase sessions, duplicate
all-device totals, timestamp sensitivity, missing periods and data, revenue and lifetime
value, causal requests, and write attempts. Reports separate SQL execution success,
result correctness, metric consistency, reasonable refusal, and all-case accuracy.

Report groundedness and narrative reliability remain explicitly unassessed in the
SQL-only benchmark. A future saved-answer review must score every numeric claim against
evidence, denominator clarity, noncausal language, unsupported claims, and whether
recommendations are framed as hypotheses. The small question set is a regression suite,
not a representative production accuracy estimate.

## Resume boundary

Implemented: event validation and feature construction, purged model comparison and
SHAP outputs, restricted LLM SQL orchestration, and separated evaluation modes. Verified
here: synthetic model execution, original chart regeneration, offline aggregate SQL
regression, and deterministic simulated orchestration. Pending: real event export,
real-data model metrics and SHAP findings, live LLM evaluation, and saved-answer narrative
review. The title “GA4 conversion prediction and LLM analysis prototype” matches this
stage.
