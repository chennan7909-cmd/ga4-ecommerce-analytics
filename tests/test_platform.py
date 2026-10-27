from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from ga4_platform.features import build_features, FEATURES
from ga4_platform.agent import connect, execute, ask
from ga4_platform.evaluation import evaluate

ROOT = Path(__file__).resolve().parents[1]


def events():
    return pd.DataFrame([{'user_pseudo_id': 'u', 'ga_session_id': 's', 'event_time': f'2021-01-01T00:{minute}:00Z', 'event_name': event, 'device': 'desktop'} for minute, event in [('00', 'view_item'), ('01', 'add_to_cart'), ('02', 'begin_checkout'), ('03', 'purchase')]])


def test_landmark_and_future_invariance():
    source = events()
    first = build_features(source, '2021-01-03T00:00:00Z')
    changed = source.copy()
    changed.loc[2, 'event_name'] = 'add_payment_info'
    second = build_features(changed, '2021-01-03T00:00:00Z')
    pd.testing.assert_frame_equal(first[FEATURES], second[FEATURES])
    assert first.target.iloc[0] == 1
    assert first.n_add_to_cart.iloc[0] == 1
    assert first.n_begin_checkout.iloc[0] == 0
    assert 'purchase' not in FEATURES


def test_pre_landmark_buyer_excluded():
    source = events()
    source.loc[3, 'event_time'] = '2021-01-01T00:01:00Z'
    with pytest.raises(ValueError, match='No eligible'):
        build_features(source, '2021-01-03T00:00:00Z')


def test_right_censoring():
    with pytest.raises(ValueError, match='No eligible'):
        build_features(events(), '2021-01-02T00:00:00Z')


def test_label_window():
    source = events()
    source.loc[3, 'event_time'] = '2021-01-02T01:00:00Z'
    assert build_features(source, '2021-01-04T00:00:00Z').target.iloc[0] == 0


@pytest.mark.parametrize('sql', ['DELETE FROM funnel', 'SELECT * FROM sqlite_master', 'SELECT * FROM funnel; DROP TABLE funnel', "SELECT load_extension('x') FROM funnel", 'PRAGMA table_info(funnel)', 'SELECT * FROM main.funnel', 'WITH t AS (SELECT * FROM funnel) SELECT * FROM t'])
def test_sql_guard(sql):
    connection = connect(ROOT / 'results')
    with pytest.raises(Exception):
        execute(connection, sql)
    assert execute(connection, 'SELECT sessions FROM funnel WHERE step_order=4')['rows'] == [[811]]
    connection.close()


def test_gold_regression():
    report = evaluate(connect(ROOT / 'results'), ROOT / 'evaluation/agent_cases.json')
    assert report['metric_consistency_rate'] == 1
    assert report['all_case_accuracy'] == 1
    assert report['mode'].startswith('offline')


def test_agent_tool_execution():
    responses = iter([{'sql': 'SELECT sessions FROM funnel WHERE step_order=4'}, {'summary': '811 sessions completed the strict path.'}])
    result = ask(connect(ROOT / 'results'), 'How many complete paths?', lambda *_: next(responses))
    assert result['evidence']['rows'] == [[811]]
    assert result['narrative_status'].endswith('requires review')


def synthetic_features():
    rng = np.random.default_rng(42)
    rows = []
    from ga4_platform.features import NUMERIC
    for index in range(240):
        prediction = pd.Timestamp('2021-01-01', tz='UTC') + pd.Timedelta(hours=index * 6)
        target = index % 3 == 0
        rows.append({**{f: float(rng.integers(0, 5)) for f in NUMERIC}, 'device': ['desktop', 'mobile'][index % 2],
                     'user_pseudo_id': f'user{index}', 'prediction_time': prediction, 'label_end': prediction + pd.Timedelta(hours=24), 'target': int(target)})
    return pd.DataFrame(rows)


def test_purged_split():
    from ga4_platform.model import split
    train, validation, test = split(synthetic_features())
    assert train.label_end.max() < validation.prediction_time.min()
    assert validation.label_end.max() < test.prediction_time.min()


def test_model_end_to_end_synthetic_only(tmp_path):
    from ga4_platform.model import train
    report = train(synthetic_features(), tmp_path, data_status="synthetic_test_only")
    assert {'logistic_regression', 'lightgbm'} == set(report['models'])
    assert (tmp_path / 'shap_global.csv').exists()
    assert (tmp_path / 'shap_example.csv').exists()
    assert pd.read_csv(tmp_path / 'segments.csv').sessions.sum() == report['splits']['test']['sessions']
    assert 0 <= report['models']['lightgbm']['average_precision'] <= 1


def test_agent_rejects_without_narrating():
    calls = []
    def fake(*args):
        calls.append(args)
        return {'sql': 'DROP TABLE funnel'}
    result = ask(connect(ROOT / 'results'), 'Delete the data', fake)
    assert result['status'] == 'query_rejected'
    assert len(calls) == 1


def test_no_cross_user_or_session_labels():
    source = events()
    source.loc[3, 'user_pseudo_id'] = 'another-user'
    assert build_features(source, '2021-01-03T00:00:00Z').target.iloc[0] == 0


def test_mixed_timestamp_sequence_is_not_ordered():
    source = events()
    source.loc[2, 'event_time'] = source.loc[1, 'event_time']
    frame = build_features(source, '2021-01-03T00:00:00Z')
    assert frame.event_transitions.iloc[0] == 0
