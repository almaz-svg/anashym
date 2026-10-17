"""Offline acceptance scoring. No provider requests or message persistence.

Inputs must be synthetic, pre-annotated cases and independently captured model
predictions. Expected answers must never be used as provider responses.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re


def pair(row):
    product = row.get('product_id')
    quantity = row.get('quantity')
    if not isinstance(product, str) or not product or not isinstance(quantity, str):
        return None
    if not re.fullmatch(r'\d+(?:\.\d+)?', quantity):
        return None
    try:
        amount = Decimal(quantity)
    except InvalidOperation:
        return None
    return (product, amount) if amount > 0 else None


def _clarified(expected, prediction):
    """Mechanical checks only; a human must also verify question relevance."""
    rows = prediction.get('items', [])
    if not isinstance(rows, list) or len(rows) != len(expected['items']):
        return False
    if not any(isinstance(q, str) and q.strip() for q in prediction.get('questions', [])):
        return False
    # The benchmark stores ambiguous items in message order. Known values must
    # survive while every annotated unresolved field remains null.
    for want, got in zip(expected['items'], rows):
        if not isinstance(got, dict):
            return False
        for field in want.get('unresolved_fields', []):
            if got.get(field, 'missing') is not None:
                return False
        for field in ('product_id', 'quantity'):
            if want.get(field) is not None and got.get(field) != want[field]:
                return False
    if expected.get('date_unresolved'):
        return prediction.get('delivery_date', 'missing') is None
    return prediction.get('delivery_date') == expected['delivery_date']


def evaluate(cases, predictions, clarification_reviews=None):
    ids = [case['id'] for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError('Benchmark case IDs must be unique')
    tp = fp = fn = ambiguous = clarified = dates = date_total = 0
    missing = []
    pending_reviews = []
    rejected_reviews = []
    clarification_reviews = clarification_reviews or {}
    for case in cases:
        prediction = predictions.get(case['id'])
        if not isinstance(prediction, dict):
            missing.append(case['id'])
            prediction = {}
        expected = case['expected']
        if case.get('ambiguous', False):
            ambiguous += 1
            clarified += int(_clarified(expected, prediction))
            if clarification_reviews.get(case['id']) is False:
                rejected_reviews.append(case['id'])
            elif clarification_reviews.get(case['id']) is not True:
                pending_reviews.append(case['id'])
            continue
        wants = Counter(pair(row) for row in expected['items'])
        if None in wants:
            raise ValueError('Unambiguous references require product and positive quantity')
        rows = prediction.get('items', [])
        if not isinstance(rows, list):
            rows = []
        # A question on an otherwise unambiguous sample cannot improve the score
        # by excluding it from evaluation. Unresolved/invalid rows count as errors.
        asks = bool(prediction.get('questions'))
        valid = [pair(row) if isinstance(row, dict) and not row.get('issues') and not asks else None for row in rows]
        actual = Counter(value for value in valid if value is not None)
        matched = sum((wants & actual).values())
        tp += matched
        fp += len(rows) - matched
        fn += sum(wants.values()) - matched
        date_total += 1
        dates += int(prediction.get('delivery_date') == expected['delivery_date'])
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    return {
        'passed': precision >= .9 and recall >= .9 and clarified == ambiguous and not missing and not pending_reviews and not rejected_reviews,
        'true_positives': tp, 'false_positives': fp, 'false_negatives': fn,
        'precision': precision, 'recall': recall,
        'ambiguities_passed': clarified, 'ambiguities_total': ambiguous,
        'dates_correct': dates, 'dates_total': date_total,
        'missing_predictions': missing,
        'pending_clarification_reviews': pending_reviews,
        'rejected_clarification_reviews': rejected_reviews,
        'question_relevance_requires_human_review': True,
    }
