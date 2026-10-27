import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description='GA4 prediction and grounded analysis')
    commands = parser.add_subparsers(dest='command', required=True)
    feature = commands.add_parser('features')
    feature.add_argument('--events', required=True)
    feature.add_argument('--observation-end', required=True, help='Exclusive UTC source boundary, e.g. 2021-02-01T00:00:00Z')
    feature.add_argument('--output', default='data/processed/features.csv')
    model = commands.add_parser('train')
    model.add_argument('--features', required=True)
    model.add_argument('--output', default='artifacts/model')
    for name in ['ask', 'evaluate-agent']:
        sub = commands.add_parser(name)
        sub.add_argument('--results', default='results')
        sub.add_argument('--segments')
        if name == 'ask':
            sub.add_argument('question')
        else:
            sub.add_argument('--cases', default='evaluation/agent_cases.json')
            sub.add_argument('--live', action='store_true', help='Send benchmark questions to configured LLM; incurs API usage')
            sub.add_argument('--output', default='artifacts/agent_evaluation.json')
    args = parser.parse_args()
    if args.command == 'features':
        from .features import build_features
        frame = build_features(pd.read_csv(args.events, dtype={'user_pseudo_id': str, 'ga_session_id': str}), args.observation_end)
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.output, index=False)
        print(json.dumps({'eligible_sessions': len(frame), 'positives': int(frame.target.sum()), 'output': args.output}))
    elif args.command == 'train':
        from .model import train
        print(json.dumps(train(pd.read_csv(args.features, dtype={'user_pseudo_id': str, 'ga_session_id': str}), args.output), indent=2))
    else:
        from .agent import connect, ask, LLM
        connection = connect(args.results, args.segments)
        try:
            if args.command == 'ask':
                print(json.dumps(ask(connection, args.question, LLM()), indent=2))
            else:
                from .evaluation import evaluate
                result = evaluate(connection, args.cases, LLM() if args.live else None)
                Path(args.output).parent.mkdir(parents=True, exist_ok=True)
                Path(args.output).write_text(json.dumps(result, indent=2))
                print(json.dumps(result, indent=2))
        finally:
            connection.close()

if __name__ == '__main__':
    main()
