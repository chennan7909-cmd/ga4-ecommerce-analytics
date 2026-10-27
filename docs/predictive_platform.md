# GA4 conversion prediction and LLM analysis

## Implementation and evidence status

The repository now contains executable feature construction, temporal model evaluation,
SHAP explanation, device/risk-band summaries, an LLM SQL analysis command, and an
agent SQL benchmark. It is a command-line research prototype, not a deployed web
platform. There is no production inference endpoint or saved model service.

Real GA4 model training has **not** been executed: the repository contains aggregate
CSV results, not the required event-level export. No GA4 prediction performance,
SHAP business finding, high-value customer identification, or measured intervention
lift is claimed. Model plumbing is tested using explicitly synthetic fixtures only.
The LLM adapter has **not** been run against a live API in this implementation session.
Offline gold SQL checks verify the analytics layer, not LLM generation capability.

## Install

Python 3.11 or 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q
```

The original chart-generation dependencies remain in requirements.txt. Install those
separately if reproducing the original charts. No credentials are required for tests.

## Event export and target

Run sql/06_prediction_events.sql in BigQuery using your own billing project, then
export the complete result as data/raw/events.csv. The query retains the original six
shopping-event types. Check BigQuery's estimated bytes before execution; this project
does not automatically run or pay for source queries. Do not commit event identities.
Required columns: user_pseudo_id, ga_session_id, event_time (UTC timestamp), event_name,
and device. transaction_id is exported for potential future diagnostics, not used as
a feature. Product IDs and page views are not available in this feature contract.

```bash
python -m ga4_platform.cli features \
  --events data/raw/events.csv \
  --observation-end 2021-02-01T00:00:00Z
python -m ga4_platform.cli train --features data/processed/features.csv
```

One example per (user_pseudo_id, ga_session_id): first view_item + 60 seconds is the
prediction landmark. The label is any purchase **strictly after** the landmark and
within the following 24 hours in that same session. Buyers at/before the landmark
are excluded. Sessions without a full label observation window are excluded.
observation-end is an exclusive source boundary, not the maximum observed event time.
The caller must guarantee complete source partitions; code cannot detect missing
source exports. This target does not capture cross-session conversion or lifetime value.
It also cannot identify genuine abandonment, and an observed purchase is not necessarily
a deduplicated commercial transaction in this obfuscated sample.

Features are six-event-scope interaction counts (excluding purchase), active time,
mean event interval, unambiguous event-type transitions, and device at first view.
Equal-timestamp mixed event groups do not receive an invented sequence order.
No full-session duration, future checkout, purchase amount, raw user ID, session ID,
or purchase event count enters the model. Short sessions without later observed activity
remain eligible if their source observation window is complete.

The resulting population is a subset of the original 23,191 shopping sessions and
must be measured after export. 121,524 event rows are source scope, not training examples.

## Models and outputs

Chronological 60/20/20 splits are purged so training labels end before validation
starts and validation labels end before test starts. Preprocessing fits only on train.
Each split must have both target classes. Split sizes and user overlap are reported;
this estimates future sessions, not an unseen-user generalization claim. One month
may be insufficient: expand the fully observed date range if splits are too small.

Compare a constant probability baseline, Logistic Regression, and LightGBM. Fixed
hyperparameters avoid tuning on test. F1 thresholds are selected on validation only.
Average Precision is reported explicitly; it is not trapezoidal PR-AUC. Also report
Precision, Recall, F1, Brier score, calibration bins, Precision@Top10%, and Lift@Top10%.
Top-k rounds up; ties use stable chronological order and may influence small samples.
These metrics assess prediction, not incremental marketing response or causal lift.

artifacts/model/ contains metrics.json, test_predictions.csv (row ordinals, no user
identities), shap_global.csv, shap_example.csv, and segments.csv. SHAP describes the
LightGBM raw log-odds contribution. The example is the first held-out row, not a
selected success case. At most 500 held-out rows contribute to global explanations.
The low/medium/high bands use fixed probability boundaries 0.1 and 0.5; they are
illustrative, not validated campaign thresholds. Segments are held-out model results,
not the original aggregate population. No synthetic output is published as GA4 evidence.

## LLM SQL analysis

The source warehouse is BigQuery. The Agent executes SQLite SQL against a local copy
of **recorded aggregate results**; it does not execute arbitrary SQL against BigQuery.
This makes business metrics inspectable without sending raw event identities externally.
The optional model segment table is also aggregate-only.

Set OPENAI_API_KEY and OPENAI_MODEL in your environment; never commit them. The adapter
uses the OpenAI Chat Completions JSON response interface. Choose an account-available
model supporting that interface. API calls require connectivity and may incur charges.

```bash
python -m ga4_platform.cli ask 'Which device has the lowest strict complete-path rate?'
python -m ga4_platform.cli ask --segments artifacts/model/segments.csv \
  'Compare observed purchase rates across model probability bands.'
```

Flow: question → LLM SQL JSON → AST validation → read-only SQLite tool execution →
LLM narrative grounded in the returned evidence. The CLI performs the tool orchestration;
it is not a general autonomous agent or native function-calling protocol. Only named
analytics tables are allowed. Multiple statements, CTEs, schema access, write statements,
and unapproved functions are rejected. SQLite authorizer and query_only provide
additional enforcement, a progress budget limits work, and output is capped at 200 rows.
There is no automatic SQL repair loop. Invalid/unavailable queries fail closed without
a narrative. Run in a separate process/container before exposing it to untrusted public traffic.

The authoritative result is SQL plus returned rows. Generated prose is clearly marked
as requiring review; prompting alone cannot guarantee factuality. The second API call
sends the question, SQL, and returned aggregate rows to the configured provider.

## Dual evaluation

```bash
# Offline regression of gold SQL and expected metrics. No model calls.
python -m ga4_platform.cli evaluate-agent
# Actual SQL-generation benchmark; requires credentials and incurs API usage.
python -m ga4_platform.cli evaluate-agent --live \
  --output artifacts/agent_live_evaluation.json
```

The eight-case starter set covers scope, strict completion, denominator, device filtering,
reconciliation, and refusal of unsupported revenue/causal requests. Six cases execute
SQL; two test unsupported answers. Report execution success and exact-result consistency
separately. Unsupported cases count only toward all-case accuracy. This small benchmark
is a smoke test, not a representative production success-rate estimate. Expand with
paraphrases, adversarial questions, and a held-out set before claiming Agent accuracy.

Narrative reliability is currently a manual evaluation dimension, not an automated score.
For each saved ask result, review: every numeric claim matches evidence; denominator and
population are explicit; descriptive comparisons avoid causality; unavailable quantities
are not invented; recommendations are framed as hypotheses. Record each criterion as
pass/fail, retain the question/SQL/result/answer, and report pass counts and denominators.
Do not claim narrative reliability from the SQL benchmark alone.

## Resume boundary

Implemented: prediction/SHAP pipeline, restricted LLM SQL orchestration, SQL metric checks.
Verified here: synthetic end-to-end model execution and offline aggregate SQL regression.
Pending: real event export, real-data model metrics, live LLM evaluation, narrative review.
The title “GA4 conversion prediction and LLM analysis prototype” matches this stage.
