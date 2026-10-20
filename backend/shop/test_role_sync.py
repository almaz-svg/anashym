"""The same delivery and confirmed money must be visible to every permitted role."""
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Batch, Client, DeliveryPoint, Order, Payment, Photo, Product, User


class RoleSyncTests(TestCase):
    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 10, 19, 10))
        clock = patch('django.utils.timezone.now', return_value=self.now)
        clock.start()
        self.addCleanup(clock.stop)
        self.company = Client.objects.create(name='Sync cafe', approval_status='active',
            deferred_approved=True, credit_limit=10000, period_start=self.now.date())
        self.users = {role: User.objects.create_user(username='sync-'+role, role=role,
            first_name=role.title(), client=self.company if role=='customer' else None)
            for role in ['customer','admin','courier','cashier','accountant']}
        self.other_courier = User.objects.create_user(username='other-courier', role='courier')
        self.point = DeliveryPoint.objects.create(client=self.company, address='Абая 25', recipient='Тест', phone='+77019999999')
        self.product = Product.objects.create(name='Sync cake', price=500)
        Batch.objects.create(product=self.product, quantity=20, manufactured_at=self.now-timedelta(hours=1), expires_at=self.now+timedelta(days=2))
        self.api = APIClient()

    def post(self, role, path, data, key=None):
        self.api.force_authenticate(self.users[role])
        return self.api.post('/api/v1/'+path, data, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def create_order(self, mode):
        response = self.post('customer', 'orders', {'kind':'regular', 'payment_mode':mode,
            'delivery_point_id':str(self.point.pk), 'requested_delivery_at':self.now.replace(hour=15).isoformat(),
            'items':[{'product_id':str(self.product.pk),'quantity':1,'expected_unit_price':'500'}]})
        self.assertEqual(response.status_code,201,response.content)
        return response.json()

    def ready_order(self, mode):
        order=self.create_order(mode)
        for state in ['preparing','ready']:
            response=self.post('admin',f"orders/{order['id']}/transition",{'status':state,'courier_id':str(self.users['courier'].pk),'version':order['version']})
            self.assertEqual(response.status_code,200,response.content)
            order=response.json()
        return order

    def deliver(self, order, cash='0'):
        response=self.post('courier',f"orders/{order['id']}/transition",{'status':'out_for_delivery','version':order['version']})
        self.assertEqual(response.status_code,200,response.content)
        order=response.json()
        photo=Photo.objects.create(order_id=order['id'],uploaded_by=self.users['courier'],purpose='delivery',file='private/sync.png',content_hash='d'*64,mime='image/png',size=1)
        payload={'version':order['version'],'photo_ids':[str(photo.pk)],'items':[{'product_id':str(self.product.pk),'quantity':1}], 'cash_received_amount':cash}
        key=str(uuid.uuid4())
        response=self.post('courier',f"orders/{order['id']}/delivery",payload,key)
        self.assertEqual(response.status_code,200,response.content)
        replay=self.post('courier',f"orders/{order['id']}/delivery",payload,key)
        self.assertEqual(replay.status_code,200,replay.content)
        return response.json()

    def assert_shared_money(self, order, cash, kaspi, due):
        for role in self.users:
            with self.subTest(role=role):
                self.api.force_authenticate(self.users[role])
                detail=self.api.get(f"/api/v1/orders/{order['id']}")
                self.assertEqual(detail.status_code,200,detail.content)
                query='?history=delivered' if role=='courier' else ''
                listed=self.api.get('/api/v1/orders'+query).json()['items']
                summary=next(row for row in listed if row['id']==order['id'])
                for row in [detail.json(),summary]:
                    self.assertEqual(row['status'],'delivered')
                    self.assertEqual(row['courier_name'],'Courier')
                    self.assertEqual(Decimal(row['cash_paid_amount']),Decimal(cash))
                    self.assertEqual(Decimal(row['kaspi_paid_amount']),Decimal(kaspi))
                    self.assertEqual(Decimal(row['outstanding_amount']),Decimal(due))
                if role in ['cashier','accountant']:
                    self.assertEqual(detail.json()['address_snapshot'],{})

    def test_cash_delivery_and_handover_are_shared_without_duplicate_payment(self):
        order=self.ready_order('cash')
        self.api.force_authenticate(self.other_courier)
        self.assertEqual(self.api.get('/api/v1/orders').json()['items'],[])
        self.assertEqual(self.api.get(f"/api/v1/orders/{order['id']}").status_code,404)
        order=self.deliver(order,'500')
        self.assert_shared_money(order,'500','0','0')
        self.assertEqual(Payment.objects.count(),1)
        handover=self.post('courier','handovers',{'amount':'500'})
        self.assertEqual(handover.status_code,201,handover.content)
        received=self.post('cashier',f"handovers/{handover.json()['id']}/confirm",{'amount':'500'})
        self.assertEqual(received.status_code,200,received.content)
        self.assert_shared_money(order,'500','0','0')
        self.assertEqual(Payment.objects.count(),1)
        self.company.refresh_from_db()
        self.assertEqual(self.company.balance,0)

    def test_deferred_delivery_and_confirmed_kaspi_show_actual_payment_method(self):
        order=self.deliver(self.ready_order('deferred'))
        self.assert_shared_money(order,'0','0','500')
        proof=Photo.objects.create(order_id=order['id'],uploaded_by=self.users['customer'],purpose='payment',file='private/kaspi.png',content_hash='p'*64,mime='image/png',size=1)
        pending=self.post('customer','payments',{'order_id':order['id'],'method':'kaspi','amount':'200','reference':'sync-kaspi','proof_id':str(proof.pk)})
        self.assertEqual(pending.status_code,201,pending.content)
        self.assert_shared_money(order,'0','0','500')
        confirmed=self.post('cashier',f"payments/{pending.json()['id']}/confirm",{'reason':'Поступление проверено'})
        self.assertEqual(confirmed.status_code,200,confirmed.content)
        self.assert_shared_money(order,'0','200','300')
        self.company.refresh_from_db()
        self.assertEqual(self.company.balance,Decimal('300'))

    def test_confirmed_prepayment_has_the_same_breakdown_before_delivery(self):
        order=self.create_order('kaspi')
        payment=self.post('admin','payments',{'client_id':str(self.company.pk),'order_id':order['id'],'method':'kaspi','amount':'500','reference':'sync-prepaid'})
        self.assertEqual(payment.status_code,201,payment.content)
        self.assertEqual(self.post('cashier',f"payments/{payment.json()['id']}/confirm",{}).status_code,200)
        self.api.force_authenticate(self.users['customer'])
        for row in [self.api.get(f"/api/v1/orders/{order['id']}").json(),self.api.get('/api/v1/orders').json()['items'][0]]:
            self.assertEqual(Decimal(row['paid_amount']),Decimal('500'))
            self.assertEqual(Decimal(row['kaspi_paid_amount']),Decimal('500'))
            self.assertEqual(Decimal(row['cash_paid_amount']),0)
