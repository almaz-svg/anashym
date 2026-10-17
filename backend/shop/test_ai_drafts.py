from datetime import date
from django.test import SimpleTestCase, TestCase
from .models import Client, Product, User, Order, Reservation, AuditEvent, Idempotency


class DraftContractTests(SimpleTestCase):
    def setUp(self):
        self.catalog = [{'product_id': 'cake', 'name': 'Медовик', 'unit': 'portion'}]
        self.draft = {'items': [{'source_text': '2 медовика', 'product_id': 'cake', 'quantity': '2', 'unit': 'portion', 'issues': []}], 'delivery_date': '2026-10-18', 'questions': []}

    def validate(self, value):
        from .ai_drafts import validate_draft
        return validate_draft(value, self.catalog, date(2026, 10, 17))

    def test_valid_draft_and_unknown_line_are_preserved(self):
        self.assertEqual(self.validate(self.draft), self.draft)
        row = {'source_text': 'космический торт', 'product_id': None, 'quantity': None, 'unit': None, 'issues': ['Уточните товар и количество']}
        self.assertEqual(self.validate({**self.draft, 'items': [row]})['items'], [row])

    def test_model_cannot_add_price_or_unknown_product(self):
        for change in ({'price': '1'}, {'product_id': 'not-in-catalog'}):
            with self.assertRaises(ValueError):
                self.validate({**self.draft, 'items': [{**self.draft['items'][0], **change}]})

    def test_quantity_date_unit_and_size_are_checked(self):
        for field, value in [('quantity', '0'), ('quantity', '1.5'), ('quantity', '1e2'), ('quantity', 2), ('unit', 'kg'), ('issues', 'bad')]:
            with self.assertRaises(ValueError):
                self.validate({**self.draft, 'items': [{**self.draft['items'][0], field: value}]})
        for day in ('2026-10-16', 'not-a-date', '2027-12-01'):
            with self.assertRaises(ValueError): self.validate({**self.draft, 'delivery_date': day})
        with self.assertRaises(ValueError): self.validate({**self.draft, 'items': self.draft['items'] * 21})

    def test_missing_fields_and_silent_uncertainty_are_rejected(self):
        with self.assertRaises(ValueError): self.validate({'items': []})
        with self.assertRaises(ValueError):
            self.validate({**self.draft, 'items': [{**self.draft['items'][0], 'quantity': None}]})


class DraftServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='draft-admin', role='admin')
        self.customer = Client.objects.create(name='Synthetic', approval_status='active')
        self.product = Product.objects.create(name='Медовик', price='1500')

    def test_parser_gets_server_catalog_and_draft_creates_nothing(self):
        from .ai_drafts import parse_order_message
        received = {}
        def parser(payload, *, timeout):
            received.update(payload); self.assertEqual(timeout, 20)
            return {'items': [{'source_text': 'два медовика', 'product_id': str(self.product.pk), 'quantity': '2', 'unit': 'portion', 'issues': []}], 'delivery_date': None, 'questions': ['На какую дату?']}
        result = parse_order_message(self.admin, {'client_id': str(self.customer.pk), 'message': 'два медовика'}, parser=parser)
        self.assertEqual(result['items'][0]['quantity'], '2')
        self.assertEqual(set(received), {'message', 'catalog', 'reference_date', 'timezone'})
        self.assertNotIn('price', received['catalog'][0])
        for model in (Order, Reservation, AuditEvent, Idempotency): self.assertFalse(model.objects.exists())

    def test_bad_provider_response_or_exception_does_not_echo_text(self):
        from .ai_drafts import parse_order_message
        from .views import Problem
        for parser in (lambda *_a, **_k: {}, lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('PRIVATE_TEXT'))):
            with self.assertRaises(Problem) as error:
                parse_order_message(self.admin, {'client_id': str(self.customer.pk), 'message': 'PRIVATE_TEXT'}, parser=parser)
            self.assertNotIn('PRIVATE_TEXT', error.exception.message)
        self.assertFalse(AuditEvent.objects.exists())

    def test_unapproved_client_never_reaches_parser(self):
        from .ai_drafts import parse_order_message
        from .views import Problem
        self.customer.approval_status = 'pending'; self.customer.save()
        with self.assertRaises(Problem) as error:
            parse_order_message(self.admin, {'client_id': str(self.customer.pk), 'message': 'test'}, parser=lambda *_a, **_k: self.fail('Parser must not run'))
        self.assertEqual(error.exception.status, 403)
