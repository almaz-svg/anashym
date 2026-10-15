"""Product details expose safe public imagery and real dated availability."""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuditEvent, Batch, Client, Product, Quota, User


class CatalogDetailsTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.admin = User.objects.create_user(username='catalog-detail-admin', role='admin')
        self.client_org = Client.objects.create(name='Catalog company', approval_status='active')
        self.customer = User.objects.create_user(username='catalog-detail-user', client=self.client_org)
        self.api.force_authenticate(self.admin)

    def post(self, path, data=None):
        return self.api.post('/api/v1/' + path, data or {}, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def test_admin_can_create_update_archive_and_restore_product_without_destroying_stock(self):
        response = self.post('products', {'name': 'Cake', 'description': 'Chocolate', 'price_amount': '1200.00', 'image_url': 'https://images.example.com/cake.jpg', 'shelf_life_hours': 48})
        self.assertEqual(response.status_code, 201, response.content)
        product = Product.objects.get(pk=response.json()['id'])
        self.assertEqual(product.shelf_life_hours, 48)
        self.assertEqual(product.image_url, 'https://images.example.com/cake.jpg')
        update = self.post(f'products/{product.pk}', {'description': 'New description', 'shelf_life_hours': 24})
        self.assertEqual(update.status_code, 200, update.content)
        product.refresh_from_db()
        self.assertEqual(product.description, 'New description')
        changed = AuditEvent.objects.get(action='product.updated')
        self.assertEqual(changed.before['shelf_life_hours'], 48)
        self.assertEqual(changed.after['shelf_life_hours'], 24)
        now = timezone.now()
        batch = Batch.objects.create(product=product, quantity=3, manufactured_at=now-timedelta(hours=1), expires_at=now+timedelta(hours=4))
        self.assertEqual(self.post(f'products/{product.pk}/archive').status_code, 200)
        self.api.force_authenticate(self.customer)
        self.assertEqual(self.api.get('/api/v1/catalog', {'delivery_date': timezone.localdate().isoformat()}).json()['items'], [])
        self.assertTrue(Batch.objects.filter(pk=batch.pk).exists())
        self.api.force_authenticate(self.admin)
        self.assertEqual(self.post(f'products/{product.pk}/restore').status_code, 200)
        product.refresh_from_db()
        self.assertTrue(product.active)

    def test_product_image_rejects_script_data_and_credentials_urls(self):
        for url in ('javascript:alert(1)', 'data:image/svg+xml,<svg/>', 'file:///etc/passwd', 'http://example.com/a.png', 'https://user:secret@example.com/a.png'):
            with self.subTest(url=url):
                result = self.post('products', {'name': 'Unsafe', 'price': '1.00', 'image_url': url})
                self.assertEqual(result.status_code, 422, result.content)
        self.assertFalse(Product.objects.filter(name='Unsafe').exists())

    def test_catalog_includes_future_quota_dates_and_only_live_batch_expiry(self):
        now = timezone.now()
        today = timezone.localdate()
        product = Product.objects.create(name='Detailed cake', description='Fresh', price='1200.00', image_url='https://example.com/cake.jpg', shelf_life_hours=48)
        live = Batch.objects.create(product=product, quantity=10, reserved=2, manufactured_at=now-timedelta(hours=1), expires_at=now+timedelta(hours=6))
        Batch.objects.create(product=product, quantity=10, manufactured_at=now-timedelta(days=2), expires_at=now-timedelta(hours=1))
        Quota.objects.create(product=product, date=today+timedelta(days=1), quantity=12, reserved=1, cutoff=now+timedelta(hours=1))
        Quota.objects.create(product=product, date=today+timedelta(days=2), quantity=12, cutoff=now-timedelta(hours=1))
        self.api.force_authenticate(self.customer)
        response = self.api.get('/api/v1/catalog', {'delivery_date': today.isoformat()})
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()['items'][0]
        self.assertEqual(row['available_qty'], 8)
        self.assertEqual(row['shelf_life_hours'], 48)
        self.assertEqual(row['image_url'], 'https://example.com/cake.jpg')
        self.assertEqual(row['available_dates'], [today.isoformat(), (today+timedelta(days=1)).isoformat()])
        self.assertEqual([batch['id'] for batch in row['batches']], [live.pk])
        self.assertEqual(row['batches'][0]['expires_at'], live.expires_at.isoformat())

    def test_customer_cannot_change_product_details(self):
        product = Product.objects.create(name='Protected', price='1200')
        self.api.force_authenticate(self.customer)
        self.assertEqual(self.post(f'products/{product.pk}', {'price_amount': '1.00'}).status_code, 403)
        product.refresh_from_db()
        self.assertEqual(str(product.price), '1200.00')

    def test_payment_instructions_never_invent_a_seller_link(self):
        self.api.force_authenticate(self.customer)
        with patch.dict('os.environ', {'KASPI_MERCHANT_URL': ''}):
            response = self.api.get('/api/v1/payment-instructions')
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.json()['configured'])
        self.assertIsNone(response.json()['seller_url'])
        with patch.dict('os.environ', {'KASPI_MERCHANT_URL': 'https://pay.kaspi.kz/pay/example-seller'}):
            row = self.api.get('/api/v1/payment-instructions').json()
        self.assertTrue(row['configured'])
        self.assertEqual(row['seller_url'], 'https://pay.kaspi.kz/pay/example-seller')
        with patch.dict('os.environ', {'KASPI_MERCHANT_URL': 'javascript:alert(1)'}):
            row = self.api.get('/api/v1/payment-instructions').json()
        self.assertFalse(row['configured'])
        self.assertIsNone(row['seller_url'])

    def test_admin_product_pages_preserve_archive_state_and_reject_invalid_cursor(self):
        for number in range(3):
            Product.objects.create(name=f'Page {number}', price='100', active=number != 1)
        first = self.api.get('/api/v1/products', {'limit': 2}).json()
        self.assertEqual(len(first['items']), 2)
        self.assertTrue(first['next_cursor'])
        second = self.api.get('/api/v1/products', {'limit': 2, 'cursor': first['next_cursor']}).json()
        self.assertEqual(len(second['items']), 1)
        self.assertEqual(sum(not row['active'] for row in first['items']+second['items']), 1)
        self.assertEqual(self.api.get('/api/v1/products', {'cursor': 'tampered'}).status_code, 422)
