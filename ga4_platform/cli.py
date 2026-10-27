import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description='GA4 prediction and grounded analysis')
    commands = parser.add_subparsers(dest='command', required=True)
    validate_data = commands.add_parser('validate-data')
    validate_data.add_argument('--events', required=True)
    validate_data.add_argument('--observation-end', required=True)
    validate_data.add_argument('--output', default='artifacts/data_validation.json')
    feature = commands.add_parser('features')
    feature.add_argument('--events', required=True)
    feature.add_argument('--observation-end', required=True, help='Exclusive UTC source boundary, e.g. 2021-02-01T00:00:00Z')
    feature.add_argument('--output', default='data/processed/features.csv')
    model = commands.add_parser('train')
    model.add_argument('--features', required=True)
    model.add_argument('--output', default='artifacts/model')
    model.add_argument('--data-source', default='user-supplied session feature CSV')
    for name in ['ask', 'evaluate-agent']:
        sub = commands.add_parser(name)
        sub.add_argument('--results', default='results')
        sub.add_argument('--segments')
        if name == 'ask':
            sub.add_argument('question')
        else:
            sub.add_argument('--cases', default='evaluation/agent_cases.json')
            mode = sub.add_mutually_exclusive_group()
            mode.add_argument('--live', action='store_true', help='Send benchmark questions to configured LLM; incurs API usage')
            mode.add_argument('--simulate', action='store_true', help='Use deterministic fixture responses; not a real LLM evaluation')
            sub.add_argument('--output', default='artifacts/agent_evaluation.json')
    args = parser.parse_args()
    if args.command in {'validate-data', 'features'}:
        from .features import build_features, validate_event_export
        events = pd.read_csv(args.events, dtype={'user_pseudo_id': str, 'ga_session_id': str})
        validation = validate_event_export(events, args.observation_end)
        if args.command == 'validate-data':
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(json.dumps(validation, indent=2), encoding='utf-8')
            print(json.dumps({**validation, 'output': args.output}, indent=2))
            return
        frame = build_features(events, args.observation_end)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False)
        print(json.dumps({'source_validation': validation, 'model_eligible_sessions': len(frame), 'model_positives': int(frame.target.sum()), 'model_positive_rate': float(frame.target.mean()), 'output': args.output}, indent=2))
    elif args.command == 'train':
        from .model import train
        print(json.dumps(train(pd.read_csv(args.features, dtype={'user_pseudo_id': str, 'ga_session_id': str}), args.output, data_source=args.data_source), indent=2))
    else:
        from .agent import connect, ask, LLM
        connection = connect(args.results, args.segments)
        try:
            if args.command == 'ask':
                print(json.dumps(ask(connection, args.question, LLM()), indent=2))
            else:
                from .evaluation import evaluate, fixture_llm
                if args.live:
                    llm = LLM()
                    mode = 'live_llm_sql_generation'
                elif args.simulate:
                    llm = fixture_llm(args.cases)
                    mode = 'simulated_llm_sql_generation_NOT_REAL_LLM'
                else:
                    llm = None
                    mode = 'offline_gold_sql_regression_NOT_LLM_performance'
                result = evaluate(connection, args.cases, llm, mode=mode)
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(json.dumps(result, indent=2))
                print(json.dumps(result, indent=2))
        finally:
            connection.close()

if __name__ == '__main__':
    main()
