import uuid
from datetime import timedelta
from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from .test_clock import freeze_order_morning

class SliceTests(TestCase):
    def setUp(self):
        freeze_order_morning(self)
        call_command('seed_demo', verbosity=0)
        self.api = APIClient()
        self.api.post('/api/v1/auth/login', {'phone':'+77010000001','password':'DemoClient2026!'}, format='json')

    def body(self, quantity=10, price='1500.00'):
        from shop.models import DeliveryPoint, Product
        return {'kind':'regular','payment_mode':'deferred','delivery_point_id':str(DeliveryPoint.objects.first().id),'requested_delivery_at':timezone.localtime().replace(hour=15,minute=0,second=0,microsecond=0).isoformat(),'items':[{'product_id':str(Product.objects.order_by('name').first().id),'quantity':quantity,'expected_unit_price':price}]}

    def create(self, body=None, key=None):
        return self.api.post('/api/v1/orders', body or self.body(), format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def test_order_replay_reserves_once_without_creating_debt(self):
        key=str(uuid.uuid4()); body=self.body()
        first=self.create(body,key); second=self.create(body,key)
        self.assertEqual(first.status_code,201,first.json())
        self.assertEqual(first.json(),second.json())
        balance=self.api.get('/api/v1/balance').json()
        self.assertEqual(balance['balance_amount'],'0.00')
        self.assertEqual(balance['reserved_credit_amount'],'15000.00')
        self.assertEqual(balance['available_credit_amount'],'35000.00')

    def test_idempotency_changed_body_conflicts(self):
        key=str(uuid.uuid4()); self.create(key=key)
        result=self.create(self.body(1),key)
        self.assertEqual(result.status_code,409)
        self.assertEqual(result.json()['code'],'IDEMPOTENCY_CONFLICT')

    def test_price_change_leaves_no_reserves(self):
        result=self.create(self.body(price='1.00'))
        self.assertEqual(result.json()['code'],'PRICE_CHANGED')
        self.assertEqual(self.api.get('/api/v1/balance').json()['reserved_credit_amount'],'0.00')

    def test_stock_shortage_is_atomic(self):
        result=self.create(self.body(30))
        self.assertEqual(result.json()['code'],'STOCK_UNAVAILABLE')
        from shop.models import Batch
        self.assertEqual(sum(Batch.objects.values_list('reserved',flat=True)),0)

    def test_credit_limit_does_not_block_purchase(self):
        from shop.models import Client, Batch
        Client.objects.update(credit_limit='1000.00')
        self.assertEqual(self.create().status_code,201)
        self.assertEqual(sum(Batch.objects.values_list('reserved',flat=True)),10)

    def test_foreign_order_returns_404(self):
        order=self.create().json()
        from shop.models import Client,User
        other=Client.objects.create(name='Other',approval_status='active')
        user=User.objects.create_user(username='+77010000009',password='password123',client=other)
        self.api.force_authenticate(user)
        self.assertEqual(self.api.get('/api/v1/orders/'+order['id']).status_code,404)

    def test_registration_can_read_catalog_immediately(self):
        self.api.logout()
        result=self.api.post('/api/v1/auth/register',{'phone':'+77010000009','password':'Password123!','name':'Coffee','category':'coffee_shop','description':'Cafe','expected_order_quantity':10,'expected_order_frequency':'weekly'},format='json')
        self.assertEqual(result.status_code,201,result.json())
        self.api.post('/api/v1/auth/login',{'phone':'+77010000009','password':'Password123!'},format='json')
        self.assertEqual(self.api.get('/api/v1/catalog',{'delivery_date':timezone.localdate().isoformat()}).status_code,200)

    def test_anonymous_is_401(self):
        self.api.logout()
        self.assertEqual(self.api.get('/api/v1/balance').status_code,401)

    def test_expiration_releases_stock_and_credit_once(self):
        from shop.models import Order,Batch
        self.create()
        Order.objects.update(status='submitted',reservation_expires_at=timezone.now()-timedelta(seconds=1))
        call_command('expire_reservations')
        call_command('expire_reservations')
        self.assertEqual(self.api.get('/api/v1/balance').json()['reserved_credit_amount'],'0.00')
        self.assertEqual(sum(Batch.objects.values_list('reserved',flat=True)),0)
        self.assertEqual(Order.objects.get().status,'cancelled')

    def test_fefo_uses_earliest_expiry(self):
        from shop.models import Batch,Product,Reservation
        p=Product.objects.order_by('name').first()
        earliest=Batch.objects.create(product=p,manufactured_at=timezone.now()-timedelta(hours=1),expires_at=timezone.now()+timedelta(hours=2),quantity=3)
        self.create(self.body(5))
        earliest.refresh_from_db()
        self.assertEqual(earliest.reserved,3)
        self.assertEqual(Reservation.objects.filter(batch=earliest).get().quantity,3)

    def test_real_csrf_is_required_for_anonymous_login(self):
        api=APIClient(enforce_csrf_checks=True)
        self.assertEqual(api.post('/api/v1/auth/login',{'phone':'+77010000001','password':'DemoClient2026!'},format='json').status_code,403)
        self.assertEqual(api.get('/api/v1/auth/csrf').status_code,204)
        token=api.cookies['csrftoken'].value
        self.assertEqual(api.post('/api/v1/auth/login',{'phone':'+77010000001','password':'DemoClient2026!'},format='json',HTTP_X_CSRFTOKEN=token).status_code,200)

    def test_login_throttles_after_five_failed_attempts(self):
        self.api.logout()
        for attempt in range(5):
            self.assertEqual(self.api.post('/api/v1/auth/login',{'phone':'+77010000001','password':'bad'},format='json').status_code,401)
        self.assertEqual(self.api.post('/api/v1/auth/login',{'phone':'+77010000001','password':'bad'},format='json').status_code,429)

    def test_uuid_alias_duplicate_rejected_without_any_reserve(self):
        from shop.models import Batch,Order
        body=self.body(7)
        item=dict(body['items'][0]); item['product_id']=item['product_id'].replace('-','').upper()
        body['items'].append(item)
        response=self.create(body)
        self.assertEqual(response.status_code,422,response.json())
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(sum(Batch.objects.values_list('reserved',flat=True)),0)

    def test_registration_overlong_fields_rejected_before_database(self):
        self.api.logout()
        body={'phone':'+77010000009','password':'Password123!','name':'x'*201,'category':'coffee_shop','description':'Cafe','expected_order_quantity':10,'expected_order_frequency':'weekly'}
        self.assertEqual(self.api.post('/api/v1/auth/register',body,format='json').status_code,422)

    def test_period_zero_rejected_by_database(self):
        from shop.models import Client
        from django.db import IntegrityError,transaction
        with self.assertRaises(IntegrityError), transaction.atomic(): Client.objects.update(period_days=0)

