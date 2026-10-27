"""Purged temporal model evaluation with train-only preprocessing."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    auc,
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_recall_curve,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .features import FEATURES, NUMERIC


def validate_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = set(FEATURES) | {
        "user_pseudo_id",
        "ga_session_id",
        "prediction_time",
        "label_end",
        "target",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing feature columns: {sorted(missing)}")
    checked = frame.copy()
    checked["prediction_time"] = pd.to_datetime(checked.prediction_time, utc=True, errors="raise")
    checked["label_end"] = pd.to_datetime(checked.label_end, utc=True, errors="raise")
    if (checked.label_end <= checked.prediction_time).any():
        raise ValueError("Every label_end must be after prediction_time")
    if checked[["user_pseudo_id", "ga_session_id"]].isna().any().any():
        raise ValueError("Missing feature session identity")
    if checked[["user_pseudo_id", "ga_session_id"]].astype(str).apply(
        lambda column: column.str.strip().eq("")
    ).any().any():
        raise ValueError("Blank feature session identity")
    if checked.duplicated(["user_pseudo_id", "ga_session_id"]).any():
        raise ValueError("Feature data must contain one row per user/session key")
    if not set(checked.target.unique()).issubset({0, 1}):
        raise ValueError("Target must be binary")
    if checked[FEATURES].isna().any().any():
        raise ValueError("Model features contain missing values")
    if checked.device.astype(str).str.strip().eq("").any():
        raise ValueError("Device feature cannot be blank")
    numeric = checked[NUMERIC].to_numpy(dtype=float)
    if not np.isfinite(numeric).all():
        raise ValueError("Numeric model features must be finite")
    return checked.sort_values(
        ["prediction_time", "user_pseudo_id", "ga_session_id"], kind="stable"
    ).reset_index(drop=True)


def split(frame):
    frame = validate_feature_frame(frame)
    if len(frame) < 30:
        raise ValueError("Need at least 30 sessions for temporal evaluation")
    first = frame.prediction_time.iloc[int(len(frame) * 0.6)]
    second = frame.prediction_time.iloc[int(len(frame) * 0.8)]
    parts = [
        frame[(frame.prediction_time < first) & (frame.label_end < first)],
        frame[
            (frame.prediction_time >= first)
            & (frame.prediction_time < second)
            & (frame.label_end < second)
        ],
        frame[frame.prediction_time >= second],
    ]
    if any(part.empty or part.target.nunique() != 2 for part in parts):
        raise ValueError("Each purged temporal split must contain both classes; use more data")
    return parts


def metrics(y, probability, threshold):
    y = np.asarray(y, dtype=int)
    probability = np.asarray(probability, dtype=float)
    if len(y) != len(probability) or not len(y):
        raise ValueError("Targets and probabilities must be nonempty and aligned")
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError("Probabilities must be finite and in [0, 1]")
    predicted = probability >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(
        y, predicted, average="binary", zero_division=0
    )
    k = max(1, math.ceil(len(y) * 0.1))
    top = np.argsort(-probability, kind="stable")[:k]
    top_precision = float(y[top].mean())
    prevalence = float(y.mean())
    bins = []
    calibration_error = 0.0
    for index in range(10):
        lower = index / 10
        upper = (index + 1) / 10
        mask = (probability >= lower) & (
            (probability < upper) if index < 9 else (probability <= 1)
        )
        if mask.any():
            mean_probability = float(probability[mask].mean())
            observed_rate = float(y[mask].mean())
            count = int(mask.sum())
            calibration_error += count / len(y) * abs(mean_probability - observed_rate)
            bins.append(
                {
                    "lower": lower,
                    "upper": upper,
                    "count": count,
                    "mean_probability": mean_probability,
                    "observed_rate": observed_rate,
                }
            )
    curve_precision, curve_recall, _ = precision_recall_curve(y, probability)
    trapezoidal_pr_auc = float(auc(curve_recall[::-1], curve_precision[::-1]))
    return {
        "average_precision": float(average_precision_score(y, probability)),
        "trapezoidal_pr_auc": trapezoidal_pr_auc,
        "brier_score": float(brier_score_loss(y, probability)),
        "expected_calibration_error_10_bins": float(calibration_error),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "threshold": float(threshold),
        "precision_at_top_10pct": top_precision,
        "lift_at_top_10pct": top_precision / prevalence,
        "top_k": k,
        "calibration_bins": bins,
    }


def select_threshold(y, probability) -> tuple[float, dict]:
    """Choose a threshold using validation labels only.

    Maximize validation F1, then precision, then the threshold itself for a
    deterministic and conservative tie break.
    """
    probability = np.asarray(probability, dtype=float)
    candidates = np.unique(np.concatenate(([0.0, 0.5, 1.0], probability)))

    def score(threshold):
        precision, _, f1, _ = precision_recall_fscore_support(
            y, probability >= threshold, average="binary", zero_division=0
        )
        return float(f1), float(precision), float(threshold)

    threshold = float(max(candidates, key=score))
    return threshold, metrics(y, probability, threshold)


def _split_summary(part: pd.DataFrame) -> dict:
    user_counts = part.groupby("user_pseudo_id").size()
    positives = int(part.target.sum())
    return {
        "sessions": int(len(part)),
        "positives": positives,
        "positive_rate": positives / len(part),
        "distinct_users": int(part.user_pseudo_id.nunique()),
        "users_with_multiple_sessions": int((user_counts > 1).sum()),
        "sessions_from_users_with_multiple_sessions": int(user_counts[user_counts > 1].sum()),
        "prediction_start": part.prediction_time.min().isoformat(),
        "prediction_end": part.prediction_time.max().isoformat(),
        "label_end_max": part.label_end.max().isoformat(),
    }


def _write_plots(output: Path, report: dict, probabilities: dict, y_test, shap_global, segments):
    names = ["constant_baseline", "logistic_regression", "lightgbm"]
    labels = ["Constant", "Logistic", "LightGBM"]
    model_metrics = {
        "constant_baseline": report["constant_baseline"],
        **{name: report["models"][name]["test"] for name in report["models"]},
    }
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.2))
    for axis, metric, title in zip(
        axes,
        ["average_precision", "precision_at_top_10pct", "brier_score"],
        ["Average Precision", "Precision@Top10%", "Brier Score (lower is better)"],
    ):
        values = [model_metrics[name][metric] for name in names]
        axis.bar(labels, values, color=["#607080", "#2878B5", "#2A9D8F"])
        axis.set_title(title)
        axis.set_ylim(0, max(values + [0.01]) * 1.25)
        axis.tick_params(axis="x", rotation=20)
        for index, value in enumerate(values):
            axis.text(index, value, f"{value:.3f}", ha="center", va="bottom")
    fig.suptitle("Held-out Test Model Comparison")
    fig.tight_layout()
    fig.savefig(output / "model_comparison.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    fig, axis = plt.subplots(figsize=(6.5, 5.2))
    axis.plot([0, 1], [0, 1], linestyle="--", color="#607080", label="Ideal")
    for name, label, color in zip(names, labels, ["#607080", "#2878B5", "#2A9D8F"]):
        bins = model_metrics[name]["calibration_bins"]
        axis.plot(
            [item["mean_probability"] for item in bins],
            [item["observed_rate"] for item in bins],
            marker="o",
            label=label,
            color=color,
        )
    axis.set(xlabel="Mean predicted probability", ylabel="Observed purchase rate", title="Held-out Calibration")
    axis.legend()
    fig.tight_layout()
    fig.savefig(output / "calibration.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    top = shap_global.head(15).sort_values("mean_absolute_shap_log_odds")
    fig, axis = plt.subplots(figsize=(8, 5.5))
    axis.barh(top.feature, top.mean_absolute_shap_log_odds, color="#2A9D8F")
    axis.set(
        xlabel="Mean absolute SHAP value (raw log-odds)",
        title="LightGBM Global Association on Held-out Sample",
    )
    fig.tight_layout()
    fig.savefig(output / "shap_global.png", dpi=180, bbox_inches="tight")
    plt.close(fig)

    band_summary = segments.groupby("predicted_band", observed=True).agg(
        sessions=("target", "size"),
        observed_purchase_rate=("target", "mean"),
        mean_probability=("probability", "mean"),
    )
    fig, axis = plt.subplots(figsize=(7, 4.5))
    positions = np.arange(len(band_summary))
    width = 0.36
    axis.bar(positions - width / 2, band_summary.observed_purchase_rate, width, label="Observed rate")
    axis.bar(positions + width / 2, band_summary.mean_probability, width, label="Mean probability")
    axis.set_xticks(positions, [str(value) for value in band_summary.index])
    axis.set(xlabel="Model probability band", ylabel="Rate", title="Held-out Probability-Band Summary")
    axis.legend()
    fig.tight_layout()
    fig.savefig(output / "segments.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def train(
    frame,
    output,
    data_status="unverified_user_supplied_features",
    data_source="user-supplied session feature CSV",
):
    import shap

    checked = validate_feature_frame(frame)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    train_set, validation, test = split(checked)
    preprocess = ColumnTransformer(
        [
            ("numeric", StandardScaler(), NUMERIC),
            (
                "device",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                ["device"],
            ),
        ]
    )
    x_train = preprocess.fit_transform(train_set[FEATURES])
    x_validation = preprocess.transform(validation[FEATURES])
    x_test = preprocess.transform(test[FEATURES])
    models = {
        "logistic_regression": LogisticRegression(max_iter=1000, random_state=42),
        "lightgbm": LGBMClassifier(
            n_estimators=150,
            max_depth=4,
            num_leaves=15,
            min_child_samples=20,
            random_state=42,
            verbosity=-1,
            n_jobs=1,
        ),
    }
    base = float(train_set.target.mean())
    split_names = ["train", "validation", "test"]
    split_parts = [train_set, validation, test]
    report = {
        "data_status": data_status,
        "data_source": data_source,
        "target": "same-session purchase strictly after the 60-second landmark and within the next 24 hours",
        "prediction_landmark": "60 seconds after the first view_item in the session",
        "population": "valid sessions with view_item, no purchase at/before landmark, and a fully observed inclusive 24-hour label endpoint",
        "metric_note": "Average Precision is a ranking-weighted step summary and is not trapezoidal PR-AUC; both are reported separately.",
        "splits": {
            name: _split_summary(part)
            for name, part in zip(split_names, split_parts)
        },
        "purged_sessions": int(len(checked) - sum(map(len, split_parts))),
        "user_overlap": {
            "train_validation": len(set(train_set.user_pseudo_id) & set(validation.user_pseudo_id)),
            "train_test": len(set(train_set.user_pseudo_id) & set(test.user_pseudo_id)),
            "validation_test": len(set(validation.user_pseudo_id) & set(test.user_pseudo_id)),
        },
        "constant_baseline": metrics(test.target, np.full(len(test), base), 0.5),
        "models": {},
        "threshold_policy": "selected on validation only by F1, then precision, then higher threshold; test labels are never used",
        "shap_interpretation": "model association in raw log-odds, not a causal effect or customer value measure",
    }
    probability_by_model = {"constant_baseline": np.full(len(test), base)}
    for name, model in models.items():
        model.fit(x_train, train_set.target)
        validation_probability = model.predict_proba(x_validation)[:, 1]
        threshold, validation_metrics = select_threshold(
            validation.target, validation_probability
        )
        test_probability = model.predict_proba(x_test)[:, 1]
        probability_by_model[name] = test_probability
        report["models"][name] = {
            "selected_threshold": threshold,
            "validation": validation_metrics,
            "test": metrics(test.target, test_probability, threshold),
        }

    probability = probability_by_model["lightgbm"]
    pd.DataFrame(
        {
            "evaluation_row": np.arange(len(test)),
            "target": test.target.to_numpy(),
            "purchase_probability": probability,
        }
    ).to_csv(output / "test_predictions.csv", index=False)

    # SHAP values explain model raw log-odds, not causal effects or probability deltas.
    sample_size = min(500, len(x_test))
    sample = x_test[:sample_size]
    values = shap.TreeExplainer(models["lightgbm"]).shap_values(sample)
    if isinstance(values, list):
        values = values[-1]
    names = preprocess.get_feature_names_out()
    shap_global = pd.DataFrame(
        {
            "feature": names,
            "mean_absolute_shap_log_odds": np.abs(values).mean(axis=0),
        }
    ).sort_values("mean_absolute_shap_log_odds", ascending=False)
    shap_global.to_csv(output / "shap_global.csv", index=False)
    sample_probability = probability[:sample_size]
    representative = int(np.argmin(np.abs(sample_probability - np.median(sample_probability))))
    pd.DataFrame(
        {
            "evaluation_row": representative,
            "target": int(test.target.iloc[representative]),
            "purchase_probability": float(sample_probability[representative]),
            "selection_basis": "closest to median LightGBM probability in SHAP sample",
            "feature": names,
            "feature_value": sample[representative],
            "shap_log_odds": values[representative],
        }
    ).to_csv(output / "shap_example.csv", index=False)

    segments = pd.DataFrame(
        {
            "device": test.device.to_numpy(),
            "target": test.target.to_numpy(),
            "probability": probability,
        }
    )
    segments["predicted_band"] = pd.cut(
        segments.probability,
        [-0.001, 0.1, 0.5, 1],
        labels=["low", "medium", "high"],
    )
    segment_output = (
        segments.groupby(["device", "predicted_band"], observed=True)
        .agg(
            sessions=("target", "size"),
            observed_purchase_rate=("target", "mean"),
            mean_probability=("probability", "mean"),
        )
        .reset_index()
    )
    segment_output.to_csv(output / "segments.csv", index=False)
    _write_plots(
        output,
        report,
        probability_by_model,
        test.target.to_numpy(),
        shap_global,
        segments,
    )
    (output / "metrics.json").write_text(
        json.dumps(report, indent=2, allow_nan=False), encoding="utf-8"
    )
    # No raw identities or executable pickle artifacts are exported.
    return report
