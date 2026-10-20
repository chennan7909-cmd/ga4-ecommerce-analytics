#!/usr/bin/env python3
"""Generate the presentation charts from the recorded aggregate CSV results."""

from __future__ import annotations

import csv
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "ga4_ecommerce_matplotlib"))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, PercentFormatter


RESULTS = ROOT / "results"
FIGURES = ROOT / "reports" / "figures"
EXPECTED_STEPS = ["view_item", "add_to_cart", "begin_checkout", "purchase"]
DATE_LABEL = "January 1–31, 2021"

COLORS = {
    "navy": "#173F5F",
    "blue": "#2878B5",
    "teal": "#2A9D8F",
    "gold": "#E9C46A",
    "orange": "#F4A261",
    "ink": "#243447",
    "muted": "#607080",
    "grid": "#D9E1E8",
}


def read_csv(name: str) -> list[dict[str, str]]:
    path = RESULTS / name
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No data rows found in {path}")
    return rows


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 18,
            "axes.titleweight": "bold",
            "axes.labelcolor": COLORS["ink"],
            "axes.edgecolor": COLORS["grid"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["ink"],
            "text.color": COLORS["ink"],
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.fonttype": "none",
            "svg.hashsalt": "ga4-ecommerce-analytics",
        }
    )


def save_figure(fig: plt.Figure, stem: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    for extension in ("svg", "png"):
        kwargs = {"dpi": 200} if extension == "png" else {"metadata": {"Date": None}}
        output_path = FIGURES / f"{stem}.{extension}"
        fig.savefig(output_path, bbox_inches="tight", **kwargs)
        if extension == "svg":
            normalized = "\n".join(
                line.rstrip()
                for line in output_path.read_text(encoding="utf-8").splitlines()
            )
            output_path.write_text(f"{normalized}\n", encoding="utf-8")
    plt.close(fig)


def ordered_funnel_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    ordered = sorted(rows, key=lambda row: int(row["step_order"]))
    steps = [row["step_name"] for row in ordered]
    if steps != EXPECTED_STEPS:
        raise ValueError(f"Unexpected funnel steps: {steps}")
    return ordered


def plot_overall_funnel(funnel: list[dict[str, str]]) -> None:
    rows = ordered_funnel_rows(funnel)
    sessions = [int(row["sessions"]) for row in rows]
    entry = sessions[0]
    rates = [value / entry for value in sessions]
    labels = [row["step_name"].replace("_", " ").title() for row in rows]

    fig, ax = plt.subplots(figsize=(11, 6.4))
    bars = ax.barh(labels, sessions, color=[COLORS["navy"], COLORS["blue"], COLORS["teal"], COLORS["gold"]], height=0.62)
    ax.invert_yaxis()
    ax.set_xlim(0, max(sessions) * 1.22)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{int(value):,}"))
    ax.xaxis.grid(True, color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Sessions reaching each step in strict sequence")
    ax.set_title("Strict Sequential Session Funnel", loc="left", pad=32)
    ax.text(
        0,
        1.025,
        f"Entry denominator: {entry:,} valid sessions containing view_item | {DATE_LABEL}",
        transform=ax.transAxes,
        color=COLORS["muted"],
    )

    for bar, count, rate in zip(bars, sessions, rates):
        ax.text(
            bar.get_width() + max(sessions) * 0.018,
            bar.get_y() + bar.get_height() / 2,
            f"{count:,}  ({rate:.2%} of entry)",
            va="center",
            fontweight="bold",
        )

    fig.text(0.125, 0.035, "Session-level observed paths; January 2021.", color=COLORS["muted"], fontsize=9.5)
    fig.text(
        0.125,
        0.012,
        "Source: results/sequential_session_funnel_2021-01.csv",
        color=COLORS["muted"],
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.20, right=0.96, top=0.82, bottom=0.19)
    save_figure(fig, "overall_session_funnel")


def plot_device_conversion(device_funnel: list[dict[str, str]]) -> None:
    device_rows = [row for row in device_funnel if row["row_type"] == "device"]
    devices = list(dict.fromkeys(row["device_category"] for row in device_rows))
    summaries = []
    for device in devices:
        rows = ordered_funnel_rows([row for row in device_rows if row["device_category"] == device])
        entry = int(rows[0]["sessions"])
        purchases = int(rows[-1]["sessions"])
        summaries.append((device, entry, purchases, purchases / entry))

    fig, ax = plt.subplots(figsize=(10.5, 6.6))
    rates = [item[3] for item in summaries]
    bars = ax.bar(
        [item[0].title() for item in summaries],
        rates,
        color=[COLORS["navy"], COLORS["teal"], COLORS["gold"]][: len(summaries)],
        width=0.58,
    )
    upper = max(rates) * 1.52
    ax.set_ylim(0, upper)
    ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.yaxis.grid(True, color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Complete strict path purchases / view_item entry sessions")
    ax.set_title("Strict Complete-Path Conversion by Device", loc="left", pad=32)
    ax.text(
        0,
        1.025,
        f"Session-level view_item → add_to_cart → begin_checkout → purchase | {DATE_LABEL}",
        transform=ax.transAxes,
        color=COLORS["muted"],
    )

    smallest_entry = min(item[1] for item in summaries)
    for bar, (_, entry, purchases, rate) in zip(bars, summaries):
        note = "\nSmaller entry sample" if entry == smallest_entry else ""
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + upper * 0.025,
            f"{rate:.2%}\n{purchases:,} / {entry:,}{note}",
            ha="center",
            va="bottom",
            fontweight="bold",
            fontsize=10,
        )

    fig.text(
        0.11,
        0.035,
        "Descriptive comparison only; no significance or causal claim.",
        color=COLORS["muted"],
        fontsize=9.5,
    )
    fig.text(
        0.11,
        0.012,
        "Source: results/device_session_funnel_2021-01.csv (device rows only; all_devices excluded)",
        color=COLORS["muted"],
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.15, right=0.96, top=0.80, bottom=0.18)
    save_figure(fig, "device_conversion")


def plot_timestamp_sensitivity(sensitivity: list[dict[str, str]]) -> None:
    purchase_rows = [row for row in sensitivity if row["step_name"] == "purchase"]
    if len(purchase_rows) != 1:
        raise ValueError("Expected exactly one purchase row in timestamp sensitivity CSV")
    purchase = purchase_rows[0]
    entry_rows = [row for row in sensitivity if row["step_name"] == "view_item"]
    if len(entry_rows) != 1:
        raise ValueError("Expected exactly one view_item row in timestamp sensitivity CSV")
    entry = int(entry_rows[0]["strict_sessions"])
    if entry != int(entry_rows[0]["relaxed_sessions"]):
        raise ValueError("Strict and relaxed timestamp rules do not share the same entry denominator")
    rates = [int(purchase["strict_sessions"]) / entry, int(purchase["relaxed_sessions"]) / entry]
    labels = ["Strict >", "Relaxed >="]
    difference_pp = (rates[1] - rates[0]) * 100

    fig, ax = plt.subplots(figsize=(10.5, 5.8))
    bars = ax.barh(labels, rates, color=[COLORS["navy"], COLORS["orange"]], height=0.55)
    ax.invert_yaxis()
    upper = max(rates) * 1.33
    ax.set_xlim(0, upper)
    ax.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=1))
    ax.xaxis.grid(True, color=COLORS["grid"], linewidth=0.8)
    ax.set_axisbelow(True)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_xlabel("Complete four-step path purchases / view_item entry sessions")
    ax.set_title("Timestamp Sensitivity of Complete-Path Conversion", loc="left", pad=32)
    ax.text(
        0,
        1.025,
        f"Same entry denominator: {entry:,} view_item sessions | {DATE_LABEL}",
        transform=ax.transAxes,
        color=COLORS["muted"],
    )
    for bar, rate in zip(bars, rates):
        ax.text(
            bar.get_width() + upper * 0.018,
            bar.get_y() + bar.get_height() / 2,
            f"{rate:.4%}",
            va="center",
            fontweight="bold",
        )
    ax.text(
        0.99,
        0.08,
        f"Difference: {difference_pp:.4f} percentage points",
        transform=ax.transAxes,
        ha="right",
        color=COLORS["ink"],
        fontweight="bold",
    )
    fig.text(0.125, 0.035, "Equal timestamps do not establish event order.", color=COLORS["muted"], fontsize=9.5)
    fig.text(
        0.125,
        0.012,
        "Source: results/timestamp_sensitivity_2021-01.csv (purchase row)",
        color=COLORS["muted"],
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.20, right=0.96, top=0.78, bottom=0.21)
    save_figure(fig, "timestamp_sensitivity")


def validate_cross_file_totals(
    funnel: list[dict[str, str]],
    device_funnel: list[dict[str, str]],
    coverage: list[dict[str, str]],
    quality: list[dict[str, str]],
    assignment: list[dict[str, str]],
    sensitivity: list[dict[str, str]],
) -> None:
    overall = ordered_funnel_rows(funnel)
    entry = int(overall[0]["sessions"])
    for row in overall:
        recorded_rate = float(row["conversion_from_entry"])
        calculated_rate = int(row["sessions"]) / entry
        if abs(recorded_rate - calculated_rate) > 1e-12:
            raise ValueError(f"Overall entry conversion does not match counts for {row['step_name']}")

    sensitivity_rows = ordered_funnel_rows(sensitivity)
    strict_entry = int(sensitivity_rows[0]["strict_sessions"])
    relaxed_entry = int(sensitivity_rows[0]["relaxed_sessions"])
    for overall_row, row in zip(overall, sensitivity_rows):
        if int(row["strict_sessions"]) != int(overall_row["sessions"]):
            raise ValueError(f"Strict sensitivity result does not reproduce {row['step_name']}")
        for prefix, denominator in (("strict", strict_entry), ("relaxed", relaxed_entry)):
            calculated_rate = int(row[f"{prefix}_sessions"]) / denominator
            recorded_rate = float(row[f"{prefix}_conversion_from_entry"])
            if abs(recorded_rate - calculated_rate) > 1e-12:
                raise ValueError(f"{prefix.title()} sensitivity rate does not match counts for {row['step_name']}")

    device_rows = [row for row in device_funnel if row["row_type"] == "device"]
    for overall_row in overall:
        device_sum = sum(
            int(row["sessions"])
            for row in device_rows
            if row["step_name"] == overall_row["step_name"]
        )
        if device_sum != int(overall_row["sessions"]):
            raise ValueError(f"Device total does not match overall total for {overall_row['step_name']}")

    coverage_total = next(row for row in coverage if row["row_type"] == "all_devices")
    purchase_rows = [row for row in coverage if row["row_type"] == "device"]
    for field in (
        "sessions_with_purchase",
        "complete_strict_path_purchase_sessions",
        "purchase_sessions_without_complete_observed_path",
    ):
        if sum(int(row[field]) for row in purchase_rows) != int(coverage_total[field]):
            raise ValueError(f"Device purchase-path total does not reconcile for {field}")

    if int(coverage_total["complete_strict_path_purchase_sessions"]) != int(overall[-1]["sessions"]):
        raise ValueError("Complete purchase paths do not match the overall funnel purchase step")
    if int(coverage_total["sessions_with_purchase"]) != (
        int(coverage_total["complete_strict_path_purchase_sessions"])
        + int(coverage_total["purchase_sessions_without_complete_observed_path"])
    ):
        raise ValueError("Purchase path coverage does not reconcile")

    valid_sessions = int(quality[0]["valid_sessions"])
    assigned_sessions = sum(
        int(row["valid_shopping_sessions"])
        for row in assignment
        if row["row_type"] == "device"
    )
    if assigned_sessions != valid_sessions:
        raise ValueError("Device assignments do not match valid shopping sessions")


def main() -> None:
    configure_style()
    funnel = read_csv("sequential_session_funnel_2021-01.csv")
    device_funnel = read_csv("device_session_funnel_2021-01.csv")
    sensitivity = read_csv("timestamp_sensitivity_2021-01.csv")
    coverage = read_csv("device_purchase_path_coverage_2021-01.csv")
    quality = read_csv("user_session_quality_2021-01.csv")
    assignment = read_csv("device_assignment_quality_2021-01.csv")
    validate_cross_file_totals(funnel, device_funnel, coverage, quality, assignment, sensitivity)
    plot_overall_funnel(funnel)
    plot_device_conversion(device_funnel)
    plot_timestamp_sensitivity(sensitivity)
    print("Validated cross-file totals and generated 3 charts in SVG and PNG formats.")


if __name__ == "__main__":
    main()
