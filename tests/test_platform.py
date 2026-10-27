from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from ga4_platform.features import build_features, validate_event_export, FEATURES
from ga4_platform.agent import connect, execute, ask
from ga4_platform.evaluation import evaluate, fixture_llm

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


def test_inclusive_label_endpoint_requires_strictly_later_source_boundary():
    source = events()
    exact_label_end = '2021-01-02T00:01:00Z'
    with pytest.raises(ValueError, match='No eligible'):
        build_features(source, exact_label_end)


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
    assert report['reasonable_refusal_rate'] == 1
    assert report['all_case_accuracy'] == 1
    assert report['mode'].startswith('offline')


def test_agent_tool_execution():
    responses = iter([
        {'sql': 'SELECT sessions FROM funnel WHERE step_order=4'},
        {
            'summary': '811 sessions completed the strict path.',
            'limitations': ['Observed session path only.'],
            'suggested_next_step': 'Review the returned SQL evidence.',
        },
    ])
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
                     'user_pseudo_id': f'user{index}', 'ga_session_id': f'session{index}',
                     'prediction_time': prediction, 'label_end': prediction + pd.Timedelta(hours=24), 'target': int(target)})
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
    assert 0 <= report['models']['lightgbm']['test']['average_precision'] <= 1
    assert report['models']['lightgbm']['selected_threshold'] == report['models']['lightgbm']['validation']['threshold']
    assert report['splits']['test']['positive_rate'] > 0
    assert set(report['user_overlap']) == {'train_validation', 'train_test', 'validation_test'}
    for filename in ['model_comparison.png', 'calibration.png', 'shap_global.png', 'segments.png']:
        assert (tmp_path / filename).exists()


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


def test_exact_duplicate_rows_are_removed_but_distinct_repeats_remain():
    source = events()
    duplicate = pd.concat([source, source.iloc[[1]]], ignore_index=True)
    report = validate_event_export(duplicate, '2021-01-03T00:00:00Z')
    frame = build_features(duplicate, '2021-01-03T00:00:00Z')
    assert report['exact_duplicate_rows_removed'] == 1
    assert frame.n_add_to_cart.iloc[0] == 1
    distinct_repeat = source.iloc[[1]].copy()
    distinct_repeat['device'] = 'mobile'
    repeated = pd.concat([source, distinct_repeat], ignore_index=True)
    assert build_features(repeated, '2021-01-03T00:00:00Z').n_add_to_cart.iloc[0] == 2


def test_cross_date_session_is_grouped_and_future_session_is_not_labelled():
    source = events()
    source.loc[0, 'event_time'] = '2021-01-01T23:59:30Z'
    source.loc[1, 'event_time'] = '2021-01-02T00:00:00Z'
    source.loc[2, 'event_time'] = '2021-01-02T00:01:00Z'
    source.loc[3, 'event_time'] = '2021-01-02T00:02:00Z'
    extra = source.iloc[[3]].copy()
    extra['ga_session_id'] = 'different-session'
    extra['event_time'] = '2021-01-02T00:01:30Z'
    source = pd.concat([source, extra], ignore_index=True)
    frame = build_features(source, '2021-01-04T00:00:00Z')
    assert frame.target.iloc[0] == 1
    assert frame.n_add_to_cart.iloc[0] == 1


def test_blank_and_conflicting_landmark_devices_are_explicit():
    source = events()
    duplicate_view = source.iloc[[0]].copy()
    duplicate_view['device'] = ' '
    frame = build_features(pd.concat([source, duplicate_view]), '2021-01-03T00:00:00Z')
    assert frame.device.iloc[0] == 'desktop'
    duplicate_view['device'] = 'mobile'
    frame = build_features(pd.concat([source, duplicate_view]), '2021-01-03T00:00:00Z')
    assert frame.device.iloc[0] == 'mixed'


def test_threshold_selection_is_validation_only_and_metrics_distinguish_pr_summaries():
    from ga4_platform.model import select_threshold, metrics
    y_validation = np.array([0, 0, 1, 1])
    probability = np.array([0.1, 0.4, 0.6, 0.9])
    threshold, validation = select_threshold(y_validation, probability)
    assert threshold == validation['threshold']
    report = metrics(y_validation, probability, threshold)
    assert 'average_precision' in report
    assert 'trapezoidal_pr_auc' in report
    assert 'expected_calibration_error_10_bins' in report


def test_feature_frame_rejects_duplicate_session_keys():
    from ga4_platform.model import validate_feature_frame
    frame = synthetic_features()
    frame.loc[1, ['user_pseudo_id', 'ga_session_id']] = frame.loc[0, ['user_pseudo_id', 'ga_session_id']]
    with pytest.raises(ValueError, match='one row per'):
        validate_feature_frame(frame)


def test_query_budget_interrupts_and_missing_tables_fail_closed(tmp_path):
    connection = connect(ROOT / 'results')
    with pytest.raises(Exception):
        execute(connection, 'SELECT COUNT(*) FROM funnel', max_vm_steps=1)
    connection.close()
    with pytest.raises(FileNotFoundError, match='unavailable'):
        connect(tmp_path)


def test_llm_failures_do_not_invent_narrative():
    connection = connect(ROOT / 'results')
    failed = ask(connection, 'How many entries?', lambda *_: (_ for _ in ()).throw(TimeoutError()))
    assert failed['status'] == 'generation_failed'
    responses = iter([{'sql': 'SELECT sessions FROM funnel WHERE step_order=1'}, None])
    partial = ask(connection, 'How many entries?', lambda *_: next(responses))
    assert partial['status'] == 'executed'
    assert partial['narrative'] is None
    assert partial['evidence']['rows'] == [[23105]]
    connection.close()


def test_simulated_llm_mode_is_explicitly_not_live():
    report = evaluate(
        connect(ROOT / 'results'),
        ROOT / 'evaluation/agent_cases.json',
        fixture_llm(ROOT / 'evaluation/agent_cases.json'),
        mode='simulated_llm_sql_generation_NOT_REAL_LLM',
    )
    assert report['all_case_accuracy'] == 1
    assert 'NOT_REAL_LLM' in report['mode']
    assert report['report_groundedness'].startswith('not evaluated')


def test_bigquery_export_sql_is_restricted_to_public_source():
    import importlib.util
    module_path = ROOT / 'scripts' / 'export_prediction_events.py'
    spec = importlib.util.spec_from_file_location('prediction_export', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.validate_export_sql((ROOT / 'sql' / '06_prediction_events.sql').read_text())
    with pytest.raises(ValueError, match='may read only'):
        module.validate_export_sql('SELECT * FROM `private-project.secret.events`')
