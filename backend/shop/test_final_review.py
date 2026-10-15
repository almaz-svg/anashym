"""Independent regressions for refunded/used Kaspi prepayments and safe demo startup."""
import uuid
from decimal import Decimal
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Client, User, DeliveryPoint, Product, Order, OrderItem, LedgerEntry
from .services import allocate_advance


class PrepaymentReviewTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client = Client.objects.create(name='Prepayment review', approval_status='active')
        self.admin = User.objects.create_user(username='prepayment-admin', role='admin')
        self.api.force_authenticate(self.admin)
        self.point = DeliveryPoint.objects.create(client=self.client, address='Review', recipient='Review', phone='+77000000000')
        self.product = Product.objects.create(name='Review cake', price='1500')
        self.order = self.make_order()

    def make_order(self, status='submitted'):
        order = Order.objects.create(client=self.client, delivery_point=self.point,
            address_snapshot='{}', kind='regular', status=status, payment_mode='kaspi',
            total='1500', delivered_total='1500' if status == 'delivered' else '0',
            requested_delivery_at=timezone.now())
        OrderItem.objects.create(order=order, product=self.product, name='Review cake',
            quantity=1, unit_price='1500', delivered_quantity=1 if status == 'delivered' else 0)
        return order

    def post(self, path, data):
        return self.api.post('/api/v1/' + path, data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def pay(self, order=None, amount='1500'):
        payment = self.post('payments', {'client_id': str(self.client.pk), 'order_id': str((order or self.order).pk),
            'method': 'kaspi', 'amount': amount, 'reference': str(uuid.uuid4())})
        self.assertEqual(payment.status_code, 201, payment.content)
        result = self.post('payments/' + payment.json()['id'] + '/confirm', {'reason': 'Independent review'})
        self.assertEqual(result.status_code, 200, result.content)
        return payment.json()['id']

    def refund(self, amount):
        result = self.post('refunds', {'client_id': str(self.client.pk), 'amount': amount,
            'method': 'kaspi', 'reason': 'Return prepayment'})
        self.assertEqual(result.status_code, 201, result.content)
        result = self.post('refunds/' + result.json()['id'] + '/confirm', {'reference': str(uuid.uuid4())})
        self.assertEqual(result.status_code, 200, result.content)

    def accept(self):
        self.order.refresh_from_db()
        return self.post('orders/' + str(self.order.pk) + '/transition', {'status': 'accepted', 'version': self.order.version})

    def test_full_refund_blocks_acceptance_and_paid_status(self):
        self.pay()
        self.refund('1500')
        response = self.accept()
        self.assertEqual(response.status_code, 409, response.content)
        data = self.api.get('/api/v1/orders/' + str(self.order.pk)).json()
        self.assertEqual(data['payment_status'], 'unpaid')
        self.assertEqual(Decimal(data['paid_amount']), Decimal('0'))

    def test_partial_refund_requires_replacement_payment(self):
        self.pay()
        self.refund('500')
        response = self.accept()
        self.assertEqual(response.status_code, 409, response.content)
        data = self.api.get('/api/v1/orders/' + str(self.order.pk)).json()
        self.assertEqual(data['payment_status'], 'partial')
        self.assertEqual(Decimal(data['paid_amount']), Decimal('1000'))
        self.pay(amount='500')
        self.assertEqual(self.accept().status_code, 200)

    def test_advance_allocated_to_other_delivery_cannot_accept_order(self):
        self.pay()
        other = self.make_order(status='delivered')
        LedgerEntry.objects.create(client=self.client, order=other, kind='delivery', amount='1500', actor=self.admin, reference=str(uuid.uuid4()))
        self.client.balance = Decimal('0')
        self.client.save(update_fields=['balance'])
        allocate_advance(self.client)
        self.assertEqual(self.accept().status_code, 409)

    def test_unrelated_orders_cannot_share_one_remaining_advance(self):
        self.pay()
        other = self.make_order()
        self.pay(other)
        self.refund('1500')
        first = self.api.get('/api/v1/orders/' + str(self.order.pk)).json()
        second = self.api.get('/api/v1/orders/' + str(other.pk)).json()
        self.assertEqual(Decimal(first['paid_amount']) + Decimal(second['paid_amount']), Decimal('1500'))
        self.assertEqual(first['payment_status'], 'unpaid')
        self.assertEqual(second['payment_status'], 'paid')

    def test_refund_after_acceptance_blocks_dispatch(self):
        self.pay()
        self.assertEqual(self.accept().status_code, 200)
        self.refund('1500')
        courier = User.objects.create_user(username='prepayment-courier', role='courier')
        self.order.refresh_from_db()
        self.order.status = 'ready'
        self.order.courier = courier
        self.order.save(update_fields=['status', 'courier'])
        response = self.post('orders/' + str(self.order.pk) + '/transition', {'status': 'out_for_delivery', 'version': self.order.version})
        self.assertEqual(response.status_code, 409, response.content)

    def test_new_payment_after_full_refund_remains_available_for_new_order(self):
        old_payment = self.pay()
        self.refund('1500')
        other = self.make_order()
        new_payment = self.pay(other)
        payments = {row['id']: row for row in self.api.get('/api/v1/payments').json()['items']}
        self.assertEqual(Decimal(payments[old_payment]['unallocated_amount']), Decimal('0'))
        self.assertEqual(Decimal(payments[new_payment]['unallocated_amount']), Decimal('1500'))
        self.assertEqual(self.api.get('/api/v1/orders/' + str(other.pk)).json()['payment_status'], 'paid')

    def test_refund_then_allocated_remainder_does_not_reduce_new_payment_twice(self):
        old_payment = self.pay()
        self.refund('500')
        other = self.make_order(status='delivered')
        other.delivered_total = Decimal('1000')
        other.save(update_fields=['delivered_total'])
        LedgerEntry.objects.create(client=self.client, order=other, kind='delivery', amount='1000', actor=self.admin, reference=str(uuid.uuid4()))
        self.client.balance = Decimal('0')
        self.client.save(update_fields=['balance'])
        allocate_advance(self.client)
        new_payment = self.pay()
        payments = {row['id']: row for row in self.api.get('/api/v1/payments').json()['items']}
        self.assertEqual(Decimal(payments[old_payment]['unallocated_amount']), Decimal('0'))
        self.assertEqual(Decimal(payments[new_payment]['unallocated_amount']), Decimal('1500'))
        self.assertEqual(self.accept().status_code, 200)


class DemoStartupReviewTests(TestCase):
    def test_reseed_preserves_existing_staff_role_and_password(self):
        staff = User.objects.create_user(username='+77010000003', role='accountant', password='MyChangedPassword2026!')
        call_command('seed_demo', verbosity=0)
        staff.refresh_from_db()
        self.assertEqual(staff.role, 'accountant')
        self.assertTrue(staff.check_password('MyChangedPassword2026!'))
