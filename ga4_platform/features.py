"""Build leakage-resistant features at a fixed session prediction landmark."""

from __future__ import annotations

import pandas as pd

EVENTS = (
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
)
REQUIRED_EVENT_COLUMNS = {
    "user_pseudo_id",
    "ga_session_id",
    "event_time",
    "event_name",
    "device",
}
NUMERIC = [f"n_{event}" for event in EVENTS if event != "purchase"] + [
    "observed_events",
    "active_seconds",
    "mean_gap_seconds",
    "event_transitions",
]
FEATURES = NUMERIC + ["device"]


def prepare_events(events: pd.DataFrame, observation_end: str) -> tuple[pd.DataFrame, pd.Timestamp, dict]:
    """Validate an event export and remove only exact duplicate contract rows.

    Repeated events remain valid when any exported field differs. The reduced
    contract cannot distinguish two genuinely separate events that are identical
    in every exported field, so the duplicate count is always reported.
    """
    missing = REQUIRED_EVENT_COLUMNS - set(events.columns)
    if missing:
        raise ValueError(f"Missing event columns: {sorted(missing)}")
    frame = events.copy()
    if frame.empty:
        raise ValueError("Event export is empty")
    for column in ("user_pseudo_id", "ga_session_id"):
        invalid = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        if invalid.any():
            raise ValueError("Missing or blank session identity")
        frame[column] = frame[column].astype(str)
    frame["event_time"] = pd.to_datetime(frame.event_time, utc=True, errors="raise")
    if frame.event_time.isna().any():
        raise ValueError("Missing event timestamps")
    unsupported = sorted(set(frame.loc[~frame.event_name.isin(EVENTS), "event_name"].astype(str)))
    if unsupported:
        raise ValueError(f"Unsupported events: {unsupported}")
    end = pd.Timestamp(observation_end)
    if end.tzinfo is None:
        raise ValueError("observation_end must have a timezone")
    end = end.tz_convert("UTC")
    if (frame.event_time >= end).any():
        raise ValueError("Events reach or exceed exclusive observation_end")

    duplicate_rows = int(frame.duplicated(keep="first").sum())
    frame = frame.drop_duplicates(keep="first").copy()
    frame["device"] = frame.device.astype("string").str.strip().replace("", pd.NA)
    report = {
        "input_event_rows": int(len(events)),
        "exact_duplicate_rows_removed": duplicate_rows,
        "validated_event_rows": int(len(frame)),
        "valid_sessions": int(frame[["user_pseudo_id", "ga_session_id"]].drop_duplicates().shape[0]),
        "distinct_users": int(frame.user_pseudo_id.nunique()),
        "missing_device_rows": int(frame.device.isna().sum()),
        "event_min_time": frame.event_time.min().isoformat(),
        "event_max_time": frame.event_time.max().isoformat(),
        "exclusive_observation_end": end.isoformat(),
        "event_counts": {
            event: int(frame.event_name.eq(event).sum()) for event in EVENTS
        },
    }
    return frame, end, report


def validate_event_export(events: pd.DataFrame, observation_end: str) -> dict:
    """Return aggregate integrity diagnostics without exposing identifiers."""
    _, _, report = prepare_events(events, observation_end)
    return report


def _landmark_device(views_at_start: pd.Series) -> str:
    categories = sorted(set(views_at_start.dropna().astype(str).str.strip()) - {""})
    if not categories:
        return "unknown"
    if len(categories) == 1:
        return categories[0]
    return "mixed"


def build_features(events, observation_end, window_seconds=60, label_hours=24):
    """Predict same-session purchase in ``(landmark, landmark + label]``.

    The landmark is 60 seconds after the first ``view_item`` by default.
    Features use only events from the first view through the landmark. Sessions
    with a purchase at or before the landmark or without a fully observable
    inclusive label endpoint are excluded.
    """
    if window_seconds <= 0 or label_hours <= 0:
        raise ValueError("Observation and label windows must be positive")
    frame, end, _ = prepare_events(events, observation_end)
    rows = []
    for (user, session), group in frame.groupby(
        ["user_pseudo_id", "ga_session_id"], sort=True
    ):
        group = group.sort_values("event_time", kind="stable")
        views = group[group.event_name.eq("view_item")]
        if views.empty:
            continue
        start = views.event_time.iloc[0]
        cutoff = start + pd.Timedelta(seconds=window_seconds)
        label_end = cutoff + pd.Timedelta(hours=label_hours)
        # Source data stop strictly before end, while the label includes
        # label_end. Equality is therefore right-censored and must be excluded.
        if label_end >= end:
            continue
        purchases = group[group.event_name.eq("purchase")].event_time
        if (purchases <= cutoff).any():
            continue
        seen = group[(group.event_time >= start) & (group.event_time <= cutoff)]
        # Equal-timestamp mixed event types have unknown order. They break the
        # transition chain rather than receiving a lexical or source-row order.
        sequence = seen.groupby("event_time", sort=True).event_name.agg(
            lambda values: values.iloc[0] if values.nunique() == 1 else None
        )
        ordered_types = sequence.tolist()
        pairs = zip(ordered_types, ordered_types[1:])
        unique_times = seen.event_time.drop_duplicates().sort_values()
        mean_gap = (
            unique_times.diff().dt.total_seconds().dropna().mean()
            if len(unique_times) > 1
            else 0.0
        )
        rows.append(
            {
                "user_pseudo_id": str(user),
                "ga_session_id": str(session),
                "prediction_time": cutoff,
                "label_end": label_end,
                "target": int(((purchases > cutoff) & (purchases <= label_end)).any()),
                "device": _landmark_device(views.loc[views.event_time.eq(start), "device"]),
                **{
                    f"n_{event}": int(seen.event_name.eq(event).sum())
                    for event in EVENTS
                    if event != "purchase"
                },
                "observed_events": int(len(seen)),
                "active_seconds": float((seen.event_time.max() - start).total_seconds()),
                "mean_gap_seconds": float(mean_gap),
                "event_transitions": sum(
                    left is not None and right is not None and left != right
                    for left, right in pairs
                ),
            }
        )
    if not rows:
        raise ValueError("No eligible uncensored sessions")
    return (
        pd.DataFrame(rows)
        .sort_values(["prediction_time", "user_pseudo_id", "ga_session_id"], kind="stable")
        .reset_index(drop=True)
    )
