"""Build features only from events available at a fixed prediction landmark."""
import pandas as pd

EVENTS = ('view_item', 'add_to_cart', 'begin_checkout', 'add_shipping_info', 'add_payment_info', 'purchase')
NUMERIC = [f'n_{e}' for e in EVENTS if e != 'purchase'] + ['observed_events', 'active_seconds', 'mean_gap_seconds', 'event_transitions']
FEATURES = NUMERIC + ['device']


def build_features(events, observation_end, window_seconds=60, label_hours=24):
    """Predict purchase in (landmark, landmark+24h], within the same session.

    Exclude pre-landmark buyers and right-censored examples. label_hours bounds
    the target explicitly; this is not an unbounded session-end prediction.
    """
    if window_seconds <= 0 or label_hours <= 0:
        raise ValueError('Observation and label windows must be positive')
    required = {'user_pseudo_id', 'ga_session_id', 'event_time', 'event_name', 'device'}
    if not required.issubset(events.columns):
        raise ValueError(f'Missing event columns: {sorted(required - set(events.columns))}')
    frame = events.copy()
    if frame[['user_pseudo_id', 'ga_session_id']].isna().any().any():
        raise ValueError('Missing session identity')
    frame['event_time'] = pd.to_datetime(frame.event_time, utc=True, errors='raise')
    if frame.event_time.isna().any() or not frame.event_name.isin(EVENTS).all():
        raise ValueError('Missing timestamps or unsupported events')
    end = pd.Timestamp(observation_end)
    if end.tzinfo is None:
        raise ValueError('observation_end must have a timezone')
    if (frame.event_time >= end).any():
        raise ValueError('Events exceed exclusive observation_end')
    rows = []
    for (user, session), group in frame.groupby(['user_pseudo_id', 'ga_session_id'], sort=True):
        group = group.sort_values(['event_time', 'event_name'], kind='stable')
        views = group[group.event_name.eq('view_item')]
        if views.empty:
            continue
        start = views.event_time.iloc[0]
        cutoff = start + pd.Timedelta(seconds=window_seconds)
        label_end = cutoff + pd.Timedelta(hours=label_hours)
        if label_end >= end:
            continue
        purchases = group[group.event_name.eq('purchase')].event_time
        if (purchases <= cutoff).any():
            continue
        seen = group[(group.event_time >= start) & (group.event_time <= cutoff)]
        # Equal-timestamp events have unknown ordering; transitions count only
        # distinct, unambiguous timestamp groups with a single event type.
        sequence = seen.groupby('event_time').event_name.agg(lambda x: x.iloc[0] if x.nunique() == 1 else None)
        pairs = list(zip(sequence.tolist(), sequence.tolist()[1:]))
        devices = views[views.event_time.eq(start)].device.fillna('unknown').astype(str).unique()
        rows.append({
            'user_pseudo_id': str(user), 'ga_session_id': str(session),
            'prediction_time': cutoff, 'label_end': label_end,
            'target': int(((purchases > cutoff) & (purchases <= label_end)).any()),
            'device': devices[0] if len(devices) == 1 else 'ambiguous',
            **{f'n_{e}': int(seen.event_name.eq(e).sum()) for e in EVENTS if e != 'purchase'},
            'observed_events': len(seen),
            'active_seconds': (seen.event_time.max() - start).total_seconds(),
            'mean_gap_seconds': seen.event_time.diff().dt.total_seconds().mean() if len(seen) > 1 else 0.,
            'event_transitions': sum(a is not None and b is not None and a != b for a, b in pairs),
        })
    if not rows:
        raise ValueError('No eligible uncensored sessions')
    return pd.DataFrame(rows).sort_values('prediction_time').reset_index(drop=True)
