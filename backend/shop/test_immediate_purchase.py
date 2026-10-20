import uuid
from datetime import timedelta
from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from .test_clock import freeze_order_morning
from .models import Client, User, Product, DeliveryPoint, Order


class ImmediatePurchaseTests(TestCase):
    def setUp(self):
        freeze_order_morning(self)
        call_command('seed_demo', verbosity=0)
        self.api=APIClient()
        self.user=User.objects.get(username='+77010000001')
        self.api.force_authenticate(self.user)

    def test_pending_customer_can_buy_each_payment_mode_without_credit_approval(self):
        Client.objects.filter(pk=self.user.client_id).update(approval_status='pending',deferred_approved=False,credit_limit=0)
        self.assertEqual(self.api.get('/api/v1/catalog',{'delivery_date':timezone.localdate().isoformat()}).status_code,200)
        product=Product.objects.get(name='Медовик')
        for mode in ['deferred','cash','kaspi']:
            body={'kind':'regular','payment_mode':mode,'delivery_point_id':str(DeliveryPoint.objects.get(client=self.user.client).pk),
                  'requested_delivery_at':timezone.localtime().replace(hour=15,minute=0,second=0,microsecond=0).isoformat(),
                  'items':[{'product_id':str(product.pk),'quantity':1,'expected_unit_price':str(product.price)}]}
            response=self.api.post('/api/v1/orders',body,format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(response.status_code,201,response.content)
            self.assertEqual(response.json()['status'],'accepted')

    def test_registration_opens_access_immediately(self):
        api=APIClient()
        response=api.post('/api/v1/auth/register',{'phone':'+77019999882','password':'TestOnlyPassword123!',
            'name':'Immediate customer','category':'individual','description':'Customer',
            'expected_order_quantity':1,'expected_order_frequency':'weekly'},format='json')
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(response.json()['approval_status'],'active')

    def test_unpaid_accepted_kaspi_expires_but_cash_order_stays_accepted(self):
        point=DeliveryPoint.objects.get(client=self.user.client)
        orders=[]
        for mode in ['cash','kaspi']:
            orders.append(Order.objects.create(client=self.user.client,delivery_point=point,address_snapshot='{}',
                status='accepted',kind='regular',payment_mode=mode,total=100,
                requested_delivery_at=timezone.now(),reservation_expires_at=timezone.now()-timedelta(minutes=1)))
        call_command('expire_reservations',verbosity=0)
        for order in orders:order.refresh_from_db()
        self.assertEqual(orders[0].status,'accepted')
        self.assertEqual(orders[1].status,'cancelled')

    def test_unpaid_kaspi_cannot_enter_preparation_and_lose_payment_deadline(self):
        order=Order.objects.create(client=self.user.client,delivery_point=DeliveryPoint.objects.get(client=self.user.client),
            address_snapshot='{}',status='accepted',kind='regular',payment_mode='kaspi',total=100,
            requested_delivery_at=timezone.now(),reservation_expires_at=timezone.now()+timedelta(minutes=30))
        self.api.force_authenticate(User.objects.get(role='admin'))
        response=self.api.post('/api/v1/orders/'+str(order.pk)+'/transition',{'status':'preparing','version':order.version},
            format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,409)
        order.refresh_from_db()
        self.assertEqual(order.status,'accepted')
        self.assertIsNotNone(order.reservation_expires_at)
