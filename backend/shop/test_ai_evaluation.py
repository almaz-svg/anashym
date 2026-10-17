from django.test import SimpleTestCase


class AIEvaluationTests(SimpleTestCase):
    def sample(self, pairs):
        return {'id': 'example', 'expected': {'items': [{'product_id': p, 'quantity': q} for p, q in pairs], 'delivery_date': '2026-10-18'}}

    def prediction(self, pairs, **extra):
        return {'items': [{'product_id': p, 'quantity': q, 'issues': []} for p, q in pairs], 'delivery_date': '2026-10-18', 'questions': [], **extra}

    def test_missing_or_extra_position_fails_perfect_score(self):
        from shop.ai_evaluation import evaluate
        sample = self.sample([('cake', '2'), ('pie', '3')])
        missing = evaluate([sample], {'example': self.prediction([('cake', '2')])})
        extra = evaluate([sample], {'example': self.prediction([('cake', '2'), ('pie', '3'), ('extra', '1')])})
        self.assertFalse(missing['passed']); self.assertEqual(missing['false_negatives'], 1)
        self.assertFalse(extra['passed']); self.assertEqual(extra['false_positives'], 1)

    def test_clarification_on_unambiguous_line_is_not_excluded(self):
        from shop.ai_evaluation import evaluate
        sample = self.sample([('cake', '2')])
        result = evaluate([sample], {'example': self.prediction([('cake', None)], questions=['Сколько?'])})
        self.assertEqual(result['true_positives'], 0)
        self.assertEqual(result['false_negatives'], 1)
        self.assertFalse(result['passed'])

    def test_ninety_percent_is_required_in_precision_and_recall(self):
        from shop.ai_evaluation import evaluate
        pairs = [(str(i), '1') for i in range(10)]
        self.assertTrue(evaluate([self.sample(pairs)], {'example': self.prediction(pairs[:9])})['passed'])
        self.assertFalse(evaluate([self.sample(pairs)], {'example': self.prediction(pairs[:8])})['passed'])

    def test_numeric_quantity_strings_match_without_float(self):
        from shop.ai_evaluation import evaluate
        self.assertTrue(evaluate([self.sample([('cake', '2')])], {'example': self.prediction([('cake', '2.0')])})['passed'])

    def test_guessed_ambiguity_fails_even_with_question(self):
        from shop.ai_evaluation import evaluate
        sample = self.sample([('cake', None)])
        sample['ambiguous'] = True
        sample['expected']['items'][0]['unresolved_fields'] = ['quantity']
        prediction = self.prediction([('cake', '1')], questions=['Уточните количество'])
        result = evaluate([sample], {'example': prediction})
        self.assertEqual(result['ambiguities_passed'], 0)
        self.assertFalse(result['passed'])

    def test_ambiguity_requires_both_null_and_explicit_question(self):
        from shop.ai_evaluation import evaluate
        sample = self.sample([('cake', None)])
        sample['ambiguous'] = True
        sample['expected']['items'][0]['unresolved_fields'] = ['quantity']
        self.assertFalse(evaluate([sample], {'example': self.prediction([('cake', None)])})['passed'])
        result = evaluate([sample], {'example': self.prediction([('cake', None)], questions=['Сколько медовиков?'])})
        self.assertEqual(result['ambiguities_passed'], 1)
        # Ambiguous cases cannot establish the 90% score by themselves.
        self.assertFalse(result['passed'])

    def test_missing_prediction_and_duplicate_ids_cannot_pass(self):
        from shop.ai_evaluation import evaluate
        sample = self.sample([('cake', '2')])
        self.assertFalse(evaluate([sample], {})['passed'])
        with self.assertRaises(ValueError):
            evaluate([sample, sample], {})

    def test_unreviewed_or_irrelevant_question_cannot_pass_acceptance(self):
        from shop.ai_evaluation import evaluate
        known = self.sample([('cake', '2')])
        unclear = {'id': 'ambiguous', 'ambiguous': True, 'expected': {'items': [{'product_id': 'cake', 'quantity': None, 'unresolved_fields': ['quantity']}], 'delivery_date': '2026-10-18'}}
        predictions = {'example': self.prediction([('cake', '2')]), 'ambiguous': self.prediction([('cake', None)], questions=['Какое количество?'])}
        self.assertFalse(evaluate([known, unclear], predictions)['passed'])
        self.assertFalse(evaluate([known, unclear], predictions, {'ambiguous': False})['passed'])
        self.assertTrue(evaluate([known, unclear], predictions, {'ambiguous': True})['passed'])
