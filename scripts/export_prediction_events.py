#!/usr/bin/env python3
"""Dry-run and optionally export the approved BigQuery event query to CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import sqlglot
from sqlglot import exp


APPROVED_SOURCE = "bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*"


def validate_export_sql(query: str) -> None:
    """Permit one BigQuery SELECT over only the approved public table wildcard."""
    trees = sqlglot.parse(query, read="bigquery")
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise ValueError("Export SQL must be exactly one SELECT")
    tables = {
        table.sql(dialect="bigquery").replace("`", "")
        for table in trees[0].find_all(exp.Table)
    }
    if tables != {APPROVED_SOURCE}:
        raise ValueError(f"Export SQL may read only {APPROVED_SOURCE}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate bytes, enforce a budget, and export prediction events."
    )
    parser.add_argument("--project", required=True, help="Billing project ID")
    parser.add_argument("--sql", default="sql/06_prediction_events.sql")
    parser.add_argument("--output", default="data/raw/events.csv")
    parser.add_argument("--location", default="US")
    parser.add_argument("--max-bytes-billed", type=int, default=5_000_000_000)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run and export after the mandatory dry run; otherwise estimate only",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.max_bytes_billed <= 0:
        parser.error("--max-bytes-billed must be positive")
    try:
        from google.cloud import bigquery
    except ImportError as error:
        raise SystemExit("Install the BigQuery extra first: pip install -e '.[bigquery]'") from error

    sql_path = Path(args.sql)
    if not sql_path.is_file():
        raise SystemExit(f"SQL file not found: {sql_path}")
    query = sql_path.read_text(encoding="utf-8")
    try:
        validate_export_sql(query)
    except (ValueError, sqlglot.errors.ParseError) as error:
        raise SystemExit(str(error)) from error
    client = bigquery.Client(project=args.project, location=args.location)
    dry_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    dry_job = client.query(query, job_config=dry_config, location=args.location)
    estimated = int(dry_job.total_bytes_processed or 0)
    print(
        json.dumps(
            {
                "mode": "dry_run",
                "estimated_bytes_processed": estimated,
                "maximum_bytes_billed": args.max_bytes_billed,
                "within_budget": estimated <= args.max_bytes_billed,
            },
            indent=2,
        )
    )
    if estimated > args.max_bytes_billed:
        raise SystemExit("Dry-run estimate exceeds --max-bytes-billed; query was not executed")
    if not args.execute:
        return

    output = Path(args.output)
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Output already exists: {output}; pass --overwrite to replace it")
    output.parent.mkdir(parents=True, exist_ok=True)
    run_config = bigquery.QueryJobConfig(
        use_query_cache=True,
        maximum_bytes_billed=args.max_bytes_billed,
        labels={"workflow": "ga4-prediction-export"},
    )
    job = client.query(query, job_config=run_config, location=args.location)
    rows = job.result()
    columns = [field.name for field in rows.schema]
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        count = 0
        for row in rows:
            writer.writerow([row[column] for column in columns])
            count += 1
    print(
        json.dumps(
            {
                "mode": "executed",
                "exported_rows": count,
                "output": str(output),
                "bytes_billed": int(job.total_bytes_billed or 0),
                "cache_hit": bool(job.cache_hit),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
