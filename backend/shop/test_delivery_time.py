import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Batch, Client, DeliveryPoint, Order, Product, Quota, Reservation, User


class DeliveryTimeTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 10, 18, 12, 0))
        clock = patch('django.utils.timezone.now', return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)
        self.customer = Client.objects.create(name='Clock customer', approval_status='active')
        user = User.objects.create_user(username='clock-customer', client=self.customer)
        self.point = DeliveryPoint.objects.create(client=self.customer, address='Address', recipient='Recipient', phone='+77001112233', window_start='00:00', window_end='23:59:59')
        self.product = Product.objects.create(name='Clock cake', price=500)
        self.batch = Batch.objects.create(product=self.product, quantity=20, manufactured_at=self.now-timedelta(hours=1), expires_at=self.now+timedelta(days=3))
        self.api = APIClient()
        self.api.force_authenticate(user)

    def order(self, requested, kind='regular'):
        return self.api.post('/api/v1/orders', {'kind': kind, 'payment_mode': 'cash',
            'delivery_point_id': str(self.point.pk), 'requested_delivery_at': requested.isoformat(),
            'items': [{'product_id': str(self.product.pk), 'quantity': 1, 'expected_unit_price': '500'}]},
            format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def test_past_and_equal_times_rejected_without_order_or_reservation(self):
        for requested in [self.now-timedelta(seconds=1), self.now]:
            with self.subTest(requested=requested):
                response = self.order(requested)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertIn('requested_delivery_at', response.json()['field_errors'])
                self.assertFalse(Order.objects.exists())
                self.assertFalse(Reservation.objects.exists())
                self.batch.refresh_from_db()
                self.assertEqual(self.batch.reserved, 0)
                self.customer.refresh_from_db()
                self.assertEqual(self.customer.reserved_credit, 0)

    def test_future_second_accepted_without_added_preparation_requirement(self):
        response = self.order(self.now+timedelta(seconds=1))
        self.assertEqual(response.status_code, 201, response.content)

    def test_day_boundary_uses_current_local_day(self):
        self.clock.return_value = self.now.replace(hour=23, minute=59, second=58)
        response = self.order(self.now.replace(hour=23, minute=59, second=59))
        self.assertEqual(response.status_code, 201, response.content)
        tomorrow = self.now.replace(hour=0)+timedelta(days=1)
        Quota.objects.create(product=self.product, date=tomorrow.date(), quantity=20, cutoff=tomorrow)
        self.assertEqual(self.order(tomorrow, 'preorder').status_code, 201)
        self.clock.return_value = tomorrow
        response = self.order(tomorrow)
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn('requested_delivery_at', response.json()['field_errors'])
