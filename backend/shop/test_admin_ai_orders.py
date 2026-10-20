import uuid
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .test_clock import freeze_order_morning

from .models import AuditEvent, Batch, Client, DeliveryPoint, Idempotency, Order, Product, Reservation, User


class AdminAIOrderTests(TestCase):
    def setUp(self):
        freeze_order_morning(self)
        self.customer = Client.objects.create(name='Test customer', approval_status='active', deferred_approved=True, credit_limit='50000', period_start=timezone.localdate())
        self.customer_user = User.objects.create_user(username='+77012221111', client=self.customer)
        self.admin = User.objects.create_user(username='+77012221112', role='admin')
        self.point = DeliveryPoint.objects.create(client=self.customer, address='Test address', recipient='Recipient', phone='+77012221111')
        self.product = Product.objects.create(name='Test dessert', price='1500.25')
        self.batch = Batch.objects.create(product=self.product, manufactured_at=timezone.now()-timedelta(hours=1), expires_at=timezone.now()+timedelta(days=3), quantity=20)
        self.api = APIClient()
        self.api.force_authenticate(self.admin)
        self.body = {'client_id': str(self.customer.pk), 'kind': 'regular', 'payment_mode': 'deferred', 'delivery_point_id': str(self.point.pk), 'requested_delivery_at': timezone.localtime().replace(hour=15, minute=0, second=0, microsecond=0).isoformat(), 'items': [{'product_id': str(self.product.pk), 'quantity': 2, 'expected_unit_price': '1500.25'}]}

    def post(self, body=None, key=None):
        return self.api.post('/api/v1/orders', self.body if body is None else body, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def test_admin_owns_audit_customer_owns_order_and_reserves(self):
        response = self.post({**self.body, 'ai_used': True})
        self.assertEqual(response.status_code, 201, response.content)
        order = Order.objects.get(pk=response.json()['id'])
        self.assertEqual(order.client_id, self.customer.pk)
        self.assertEqual(order.total, Decimal('3000.50'))
        self.customer.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(self.customer.reserved_credit, Decimal('3000.50'))
        self.assertEqual(self.customer.balance, 0)
        self.assertEqual(self.batch.reserved, 2)
        events = AuditEvent.objects.filter(object_id=str(order.pk))
        self.assertTrue(events.exists())
        self.assertTrue(all(event.actor_id == self.admin.pk for event in events))
        self.assertTrue(events.get(action='order.created').details['ai_used'])

    def test_replay_is_idempotent_and_changed_ai_flag_conflicts(self):
        body = {**self.body, 'ai_used': True}; key = str(uuid.uuid4())
        first = self.post(body, key); second = self.post(body, key)
        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Reservation.objects.get().quantity, 2)
        self.assertEqual(self.post({**body, 'ai_used': False}, key).status_code, 409)

    def test_raw_message_is_rejected_without_persistence(self):
        marker = 'PRIVATE_MESSAGE_DO_NOT_STORE'
        response = self.post({**self.body, 'message': marker, 'ai_used': True})
        self.assertEqual(response.status_code, 422)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())
        self.assertFalse(Idempotency.objects.exists())

    def test_ai_flag_requires_boolean(self):
        for value in ('true', 1, None, {'message': 'private'}):
            response = self.post({**self.body, 'ai_used': value})
            self.assertEqual(response.status_code, 422)
        self.assertFalse(Order.objects.exists())

    def test_rejected_archived_or_unknown_customer_cannot_order(self):
        for field, value in [('approval_status', 'rejected'), ('archived', True)]:
            setattr(self.customer, field, value); self.customer.save()
            self.assertEqual(self.post().status_code, 403)
            setattr(self.customer, field, 'active' if field == 'approval_status' else False)
        self.assertEqual(self.post({**self.body, 'client_id': str(uuid.uuid4())}).status_code, 422)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())

    def test_other_customers_address_cannot_be_used(self):
        other = Client.objects.create(name='Other')
        point = DeliveryPoint.objects.create(client=other, address='Other address', recipient='Other', phone='+77012221113')
        self.assertEqual(self.post({**self.body, 'delivery_point_id': str(point.pk)}).status_code, 404)
        self.assertFalse(Order.objects.exists())

    def test_customer_and_staff_cannot_choose_client_or_claim_ai(self):
        cashier = User.objects.create_user(username='+77012221114', role='cashier')
        for user in (self.customer_user, cashier):
            self.api.force_authenticate(user)
            self.assertIn(self.post({**self.body, 'ai_used': True}).status_code, (403, 422))
        self.assertFalse(Order.objects.exists())

    def test_shortages_leave_no_partial_reserve(self):
        for change in ({'items': [{**self.body['items'][0], 'quantity': 21}]}, {'items': [{**self.body['items'][0], 'expected_unit_price': '1.00'}]}):
            self.assertEqual(self.post({**self.body, **change, 'ai_used': True}).status_code, 409)
        self.assertFalse(Order.objects.exists())
        self.assertFalse(Reservation.objects.exists())
        self.customer.refresh_from_db(); self.batch.refresh_from_db()
        self.assertEqual(self.customer.reserved_credit, 0)
        self.assertEqual(self.batch.reserved, 0)

    def test_manual_customer_order_still_works_without_ai_metadata(self):
        self.api.force_authenticate(self.customer_user)
        body = {k: v for k, v in self.body.items() if k != 'client_id'}
        response = self.post(body)
        self.assertEqual(response.status_code, 201, response.content)
        event = AuditEvent.objects.get(action='order.created')
        self.assertEqual(event.actor_id, self.customer_user.pk)
        self.assertFalse(event.details.get('ai_used', False))

    def test_ai_parse_is_disabled_and_does_not_store_body(self):
        response = self.api.post('/api/v1/ai/order-draft', {'message': 'PRIVATE_MESSAGE_DO_NOT_STORE'}, format='json')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['code'], 'AI_NOT_CONFIGURED')
        self.assertFalse(AuditEvent.objects.exists())
        self.assertFalse(Idempotency.objects.exists())
        self.assertFalse(Order.objects.exists())

    def test_ai_endpoint_is_admin_only(self):
        self.api.force_authenticate(self.customer_user)
        response = self.api.post('/api/v1/ai/order-draft', {'message': 'Test'}, format='json')
        self.assertEqual(response.status_code, 403)
