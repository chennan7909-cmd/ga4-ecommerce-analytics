# Prediction event data contract

## Evidence boundary

The model requires event-level rows exported from BigQuery. The aggregate CSV files in
`results/` cannot be used as model training examples. They remain the authoritative
descriptive analysis for 121,524 shopping-event rows and 23,191 valid shopping sessions;
the eligible model population must be counted again after validation, landmarking,
censoring, and buyer exclusions.

No real event export is committed to this repository. `data/raw/`, `data/processed/`,
and `artifacts/` are ignored because they may contain pseudonymous identifiers or model
outputs derived from them.

## BigQuery source and export

`sql/06_prediction_events.sql` reads the public
`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` tables for full
partitions from 2021-01-01 through 2021-01-31. It retains the same six shopping events
as the descriptive analysis and excludes rows without either session-key component.

The safe export wrapper always performs a dry run first and enforces
`maximum_bytes_billed` when execution is explicitly requested:

```bash
pip install -e '.[bigquery]'
python scripts/export_prediction_events.py \
  --project YOUR_BILLING_PROJECT \
  --max-bytes-billed 5000000000

# Only after reviewing the estimate:
python scripts/export_prediction_events.py \
  --project YOUR_BILLING_PROJECT \
  --max-bytes-billed 5000000000 \
  --execute
```

The wrapper does not print credentials. Authentication must be supplied through
Application Default Credentials or an explicitly configured environment outside the
repository. It never writes to BigQuery; the only external query is a `SELECT` against
the approved public table wildcard.

## Exported columns

| Column | Required for features | Meaning |
|---|---|---|
| `user_pseudo_id` | Yes | Pseudonymous user component of the session key; never a model feature |
| `ga_session_id` | Yes | Session component; never a model feature |
| `event_time` | Yes | UTC event timestamp |
| `event_partition` | No | Source table suffix used for partition coverage checks |
| `event_name` | Yes | One of the six approved shopping events |
| `device` | Yes | GA4 device category; blank values become `unknown` at the landmark |
| `transaction_id` | No | Diagnostic field only; never a feature or label deduplication claim |

The reduced export has no guaranteed immutable event-row identifier. Validation removes
only rows that are exact duplicates across every exported column and reports how many
were removed. Repeated events are retained when any exported field differs. Two genuine
events that are identical across the full reduced contract cannot be distinguished; this
is an explicit source limitation.

## Integrity checks

```bash
python -m ga4_platform.cli validate-data \
  --events data/raw/events.csv \
  --observation-end 2021-02-01T00:00:00Z
```

Validation fails on missing/blank session keys, invalid timestamps, unsupported event
names, or events at/after the exclusive observation boundary. Its aggregate report
contains input rows, exact duplicates removed, validated rows, valid sessions, distinct
users, missing-device rows, event counts, timestamp bounds, and the declared boundary.
It does not emit identifiers.

The caller must verify that all source partitions through the observation boundary were
exported. Code can reject rows beyond a declared boundary but cannot prove that an
upstream partition or event row is absent.

## Prediction target and exclusions

- Unit: one `(user_pseudo_id, ga_session_id)` session.
- Entry: a valid session with at least one `view_item`.
- Landmark: 60 seconds after the first `view_item`.
- Features: approved events from the first view through the landmark, inclusive;
  `purchase` is never a feature.
- Label: at least one same-session `purchase` strictly after the landmark and at or
  before the following 24-hour endpoint.
- Exclusions: purchase at/before the landmark, or an inclusive label endpoint that is
  not strictly earlier than the exclusive export boundary.
- Scope limitation: cross-session purchases are not labels, and the target is neither
  lifetime value nor causal response to an intervention.

Events from the same session are grouped across dates when present in the export. Equal
timestamps do not receive an invented order. Mixed event types at one timestamp break
the transition chain. Counts still include all validated, landmark-visible rows. Device
uses the nonblank category at the first-view timestamp; no category becomes `unknown`,
and multiple categories become `mixed`.

## Feature and model outputs

```bash
python -m ga4_platform.cli features \
  --events data/raw/events.csv \
  --observation-end 2021-02-01T00:00:00Z

python -m ga4_platform.cli train \
  --features data/processed/features.csv \
  --data-source "BigQuery public GA4 event export, 2021-01"
```

The feature command reports the newly measured eligible session count, positive count,
and positive rate. These values must not be replaced by the descriptive 23,191-session
total. Training validates one row per session key, finite features, binary labels, and
timestamp ordering before temporal splitting.
