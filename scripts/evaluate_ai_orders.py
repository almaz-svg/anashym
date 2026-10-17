"""Score synthetic benchmark predictions; this script never calls an AI service."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from shop.ai_evaluation import evaluate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('predictions', type=Path, help='JSON object mapping benchmark case IDs to actual responses')
    parser.add_argument('--benchmark', type=Path, default=Path(__file__).resolve().parents[1] / 'qa' / 'ai-orders-benchmark.json')
    parser.add_argument('--reviews', type=Path, help='Human checks of question relevance: JSON object case_id -> true/false')
    args = parser.parse_args()
    benchmark = json.loads(args.benchmark.read_text(encoding='utf-8'))
    predictions = json.loads(args.predictions.read_text(encoding='utf-8'))
    reviews = json.loads(args.reviews.read_text(encoding='utf-8')) if args.reviews else {}
    result = evaluate(benchmark['cases'], predictions, reviews)
    # Print metrics only, never the messages or provider response bodies.
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
