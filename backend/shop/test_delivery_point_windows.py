import uuid
from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Batch, Client, DeliveryPoint, Order, Product, User


class DeliveryPointWindowTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(name='Delivery window', approval_status='active')
        user = User.objects.create_user(username='window-customer', role='customer', client=self.client_record)
        self.api = APIClient()
        self.api.force_authenticate(user)

    def create_point(self, start, end):
        return self.api.post('/api/v1/delivery-points', {
            'address': 'Алматы, Абая 25', 'recipient': 'Получатель',
            'phone': '8 (701) 999-98-81', 'window_start': start, 'window_end': end,
        }, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def test_reversed_or_equal_window_is_rejected_without_inserting(self):
        for start, end in [('23:05', '00:12'), ('12:00', '12:00')]:
            with self.subTest(start=start, end=end):
                response = self.create_point(start, end)
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(set(response.json()['field_errors']), {'window_start', 'window_end'})
                self.assertFalse(DeliveryPoint.objects.filter(client=self.client_record).exists())

    def test_regular_window_is_persisted(self):
        response = self.create_point('09:00', '20:00')
        self.assertEqual(response.status_code, 201, response.content)
        point = DeliveryPoint.objects.get(pk=response.json()['id'])
        self.assertEqual((point.window_start, point.window_end), (time(9), time(20)))
        self.assertEqual(point.phone, '+77019999881')

    def test_malformed_window_is_rejected_on_its_field(self):
        response = self.create_point('25:90', '20:00')
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn('window_start', response.json()['field_errors'])
        self.assertFalse(DeliveryPoint.objects.filter(client=self.client_record).exists())

    def test_saved_window_allows_its_boundaries_and_rejects_outside_times(self):
        now = timezone.make_aware(datetime(2026, 10, 19, 8))
        with patch('django.utils.timezone.now', return_value=now):
            point = self.create_point('09:00', '20:00').json()
            product = Product.objects.create(name='Window cake', price=500)
            batch = Batch.objects.create(product=product, quantity=20,
                                         manufactured_at=now-timedelta(hours=1),
                                         expires_at=now+timedelta(days=1))
            for hour, minute, expected in [(9, 0, 201), (20, 0, 201), (8, 59, 422), (20, 1, 422)]:
                with self.subTest(hour=hour, minute=minute):
                    response = self.api.post('/api/v1/orders', {
                        'kind': 'regular', 'payment_mode': 'cash', 'delivery_point_id': point['id'],
                        'requested_delivery_at': now.replace(hour=hour, minute=minute).isoformat(),
                        'items': [{'product_id': str(product.pk), 'quantity': 1, 'expected_unit_price': '500'}],
                    }, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
                    self.assertEqual(response.status_code, expected, response.content)
            self.assertEqual(Order.objects.count(), 2)
            batch.refresh_from_db()
            self.assertEqual(batch.reserved, 2)

    def test_model_clean_rejects_non_increasing_window(self):
        for start, end in [(time(23, 5), time(0, 12)), (time(12), time(12))]:
            with self.subTest(start=start, end=end):
                point = DeliveryPoint(client=self.client_record, address='Адрес', recipient='Получатель',
                                      phone='+77019999881', window_start=start, window_end=end)
                with self.assertRaises(ValidationError) as caught:
                    point.full_clean()
                self.assertEqual(set(caught.exception.message_dict), {'window_start', 'window_end'})
