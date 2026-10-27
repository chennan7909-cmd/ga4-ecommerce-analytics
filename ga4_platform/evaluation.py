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


def evaluate(connection, cases_path, llm=None):
    cases = json.loads(open(cases_path).read())
    results = []
    for case in cases:
        record = {'id': case['id'], 'executed': False, 'correct': False}
        try:
            response = llm('Return JSON with sql or unsupported. Generate one SQLite SELECT. ' + SCHEMA, {'question': case['question']}) if llm else ({'unsupported': 'No supporting data'} if case.get('unsupported') else {'sql': case['sql']})
            if case.get('unsupported'):
                record['correct'] = bool(response.get('unsupported'))
            elif 'sql' in response:
                evidence = execute(connection, response['sql'])
                record.update(executed=True, correct=not evidence['truncated'] and equivalent(evidence['rows'], case['expected']), sql=response['sql'])
        except Exception as error:
            record['error_type'] = type(error).__name__
        results.append(record)
    executable = [r for r, case in zip(results, cases) if not case.get('unsupported')]
    return {'mode': 'live_llm_sql' if llm else 'offline_gold_sql_regression_NOT_LLM_performance',
            'sql_execution_rate': sum(r['executed'] for r in executable) / len(executable),
            'metric_consistency_rate': sum(r['correct'] for r in executable) / len(executable),
            'all_case_accuracy': sum(r['correct'] for r in results) / len(results),
            'narrative_reliability': 'not scored; manual evidence review required', 'cases': results}
