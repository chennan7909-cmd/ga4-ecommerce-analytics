"""Temporal, purged evaluation with validation-only threshold selection."""
import json
import math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, precision_recall_fscore_support, f1_score
from lightgbm import LGBMClassifier
from .features import FEATURES, NUMERIC


def split(frame):
    frame = frame.sort_values('prediction_time').copy()
    frame['prediction_time'] = pd.to_datetime(frame.prediction_time, utc=True)
    frame['label_end'] = pd.to_datetime(frame.label_end, utc=True)
    if len(frame) < 30:
        raise ValueError('Need at least 30 sessions for temporal evaluation')
    first = frame.prediction_time.iloc[int(len(frame) * .6)]
    second = frame.prediction_time.iloc[int(len(frame) * .8)]
    parts = [frame[(frame.prediction_time < first) & (frame.label_end < first)],
             frame[(frame.prediction_time >= first) & (frame.prediction_time < second) & (frame.label_end < second)],
             frame[frame.prediction_time >= second]]
    if any(p.empty or p.target.nunique() != 2 for p in parts):
        raise ValueError('Each purged temporal split must contain both classes; use more data')
    return parts


def metrics(y, probability, threshold):
    predicted = np.asarray(probability) >= threshold
    precision, recall, f1, _ = precision_recall_fscore_support(y, predicted, average='binary', zero_division=0)
    k = max(1, math.ceil(len(y) * .1))
    top = np.argsort(-np.asarray(probability), kind='stable')[:k]
    top_precision = float(np.asarray(y)[top].mean())
    bins = []
    for i in range(10):
        mask = (probability >= i / 10) & ((probability < (i + 1) / 10) if i < 9 else (probability <= 1))
        if mask.any():
            bins.append({'count': int(mask.sum()), 'mean_probability': float(probability[mask].mean()), 'observed_rate': float(np.asarray(y)[mask].mean())})
    return {'average_precision': float(average_precision_score(y, probability)),
            'brier_score': float(brier_score_loss(y, probability)), 'precision': float(precision),
            'recall': float(recall), 'f1': float(f1), 'threshold': float(threshold),
            'precision_at_top_10pct': top_precision, 'lift_at_top_10pct': top_precision / float(np.mean(y)),
            'top_k': k, 'calibration_bins': bins}


def train(frame, output, data_status="unverified_user_supplied_features"):
    import shap
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    train_set, validation, test = split(frame)
    preprocess = ColumnTransformer([('numeric', StandardScaler(), NUMERIC),
                                   ('device', OneHotEncoder(handle_unknown='ignore', sparse_output=False), ['device'])])
    x_train = preprocess.fit_transform(train_set[FEATURES])
    x_validation = preprocess.transform(validation[FEATURES])
    x_test = preprocess.transform(test[FEATURES])
    models = {'logistic_regression': LogisticRegression(max_iter=1000, random_state=42),
              'lightgbm': LGBMClassifier(n_estimators=150, max_depth=4, num_leaves=15, min_child_samples=20, random_state=42, verbosity=-1, n_jobs=1)}
    base = float(train_set.target.mean())
    report = {'data_status': data_status, 'target': 'same-session purchase in 24h after 60s landmark',
              'splits': {name: {'sessions': len(part), 'positives': int(part.target.sum()), 'start': str(part.prediction_time.min()), 'end': str(part.prediction_time.max())} for name, part in zip(['train', 'validation', 'test'], [train_set, validation, test])},
              'purged_sessions': len(frame) - sum(map(len, [train_set, validation, test])),
              'test_users_seen_in_train': len(set(train_set.user_pseudo_id) & set(test.user_pseudo_id)),
              'constant_baseline': metrics(test.target, np.full(len(test), base), .5), 'models': {}}
    for name, model in models.items():
        model.fit(x_train, train_set.target)
        val_prob = model.predict_proba(x_validation)[:, 1]
        candidates = np.linspace(.01, .99, 99)
        threshold = max(candidates, key=lambda t: f1_score(validation.target, val_prob >= t, zero_division=0))
        report['models'][name] = metrics(test.target, model.predict_proba(x_test)[:, 1], threshold)
    probability = models['lightgbm'].predict_proba(x_test)[:, 1]
    pd.DataFrame({'evaluation_row': np.arange(len(test)), 'target': test.target.to_numpy(), 'purchase_probability': probability}).to_csv(output / 'test_predictions.csv', index=False)
    # SHAP values explain raw log-odds, not causal effects or probability deltas.
    sample = x_test[:min(500, len(x_test))]
    values = shap.TreeExplainer(models['lightgbm']).shap_values(sample)
    if isinstance(values, list):
        values = values[-1]
    names = preprocess.get_feature_names_out()
    pd.DataFrame({'feature': names, 'mean_absolute_shap_log_odds': np.abs(values).mean(axis=0)}).sort_values('mean_absolute_shap_log_odds', ascending=False).to_csv(output / 'shap_global.csv', index=False)
    pd.DataFrame({'feature': names, 'feature_value': sample[0], 'shap_log_odds': values[0]}).to_csv(output / 'shap_example.csv', index=False)
    segments = pd.DataFrame({'device': test.device.to_numpy(), 'target': test.target.to_numpy(), 'probability': probability})
    segments['predicted_band'] = pd.cut(segments.probability, [-.001, .1, .5, 1], labels=['low', 'medium', 'high'])
    segments.groupby(['device', 'predicted_band'], observed=True).agg(sessions=('target', 'size'), observed_purchase_rate=('target', 'mean'), mean_probability=('probability', 'mean')).reset_index().to_csv(output / 'segments.csv', index=False)
    (output / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    # No raw identities or executable pickle artifacts are exported.
    return report
