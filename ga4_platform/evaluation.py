import json
import math
from .agent import execute, SCHEMA


def equivalent(actual, expected):
    if len(actual) != len(expected):
        return False
    for row, gold in zip(actual, expected):
        if len(row) != len(gold):
            return False
        for a, b in zip(row, gold):
            if isinstance(b, (int, float)):
                if not isinstance(a, (int, float)) or not math.isclose(a, b, rel_tol=1e-7, abs_tol=1e-9):
                    return False
            elif a != b:
                return False
    return True


def fixture_llm(cases_path):
    """Deterministic test double. This is never a real LLM call."""
    cases = json.loads(open(cases_path, encoding='utf-8').read())
    responses = {
        case['question']: (
            {'unsupported': 'No supporting data in the approved analytics tables.'}
            if case.get('unsupported')
            else {'sql': case['sql']}
        )
        for case in cases
    }

    def respond(_system, payload):
        return responses.get(payload['question'], {'unsupported': 'Question is outside the fixture set.'})

    return respond


def _rate(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate(connection, cases_path, llm=None, mode=None):
    cases = json.loads(open(cases_path, encoding='utf-8').read())
    if mode is None:
        mode = 'offline_gold_sql_regression_NOT_LLM_performance' if llm is None else 'live_llm_sql_generation'
    results = []
    for case in cases:
        record = {
            'id': case['id'],
            'category': case.get('category'),
            'expected_unsupported': bool(case.get('unsupported')),
            'executed': False,
            'result_correct': False,
            'refusal_correct': False,
        }
        try:
            response = llm('Return JSON with sql or unsupported. Generate one SQLite SELECT. ' + SCHEMA, {'question': case['question']}) if llm else ({'unsupported': 'No supporting data'} if case.get('unsupported') else {'sql': case['sql']})
            if case.get('unsupported'):
                record['refusal_correct'] = bool(response.get('unsupported'))
            elif 'sql' in response:
                evidence = execute(connection, response['sql'])
                record.update(
                    executed=True,
                    result_correct=not evidence['truncated'] and equivalent(evidence['rows'], case['expected']),
                    sql=response['sql'],
                    evidence=evidence,
                )
        except Exception as error:
            record['error_type'] = type(error).__name__
        results.append(record)
    executable = [r for r, case in zip(results, cases) if not case.get('unsupported')]
    refusal = [r for r, case in zip(results, cases) if case.get('unsupported')]
    correct_count = sum(r['result_correct'] or r['refusal_correct'] for r in results)
    return {
        'mode': mode,
        'case_counts': {
            'all': len(results),
            'executable': len(executable),
            'unsupported': len(refusal),
        },
        'sql_execution_success_rate': _rate(sum(r['executed'] for r in executable), len(executable)),
        'result_correctness_rate': _rate(sum(r['result_correct'] for r in executable), len(executable)),
        'metric_consistency_rate': _rate(sum(r['result_correct'] for r in executable), len(executable)),
        'reasonable_refusal_rate': _rate(sum(r['refusal_correct'] for r in refusal), len(refusal)),
        'all_case_accuracy': _rate(correct_count, len(results)),
        'report_groundedness': 'not evaluated in this SQL-generation benchmark',
        'narrative_reliability': 'not evaluated; requires a separate saved-answer evidence review',
        'cases': results,
    }
