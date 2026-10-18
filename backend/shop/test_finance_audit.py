"""Accounting conservation across manual approvals, custody and returns."""
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (Batch, CashboxMovement, CashMovement, Client, DeliveryPoint,
                     LedgerEntry, Order, OrderItem, Payment, PaymentAllocation,
                     Photo, Product, Reservation, ReturnRequest, User)
from .services import cash_available, cash_balance, post_ledger


class FinanceAuditTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client_record = Client.objects.create(name='Audit', approval_status='active')
        self.admin = User.objects.create_user(username='audit-admin', role='admin')
        self.cashier = User.objects.create_user(username='audit-cashier', role='cashier')
        self.courier = User.objects.create_user(username='audit-courier', role='courier')
        self.customer = User.objects.create_user(username='audit-customer', client=self.client_record)
        self.point = DeliveryPoint.objects.create(client=self.client_record, address='A', recipient='B', phone='1')
        self.product = Product.objects.create(name='Cake', price=100)
        self.api.force_authenticate(self.cashier)

    def post(self, path, data, key=None):
        return self.api.post('/api/v1/' + path, data, format='json', HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def order(self, delivered=True):
        order = Order.objects.create(client=self.client_record, delivery_point=self.point,
            address_snapshot='{}', kind='regular', status='delivered' if delivered else 'out_for_delivery',
            payment_mode='deferred' if delivered else 'cash', total=100,
            delivered_total=100 if delivered else 0, courier=self.courier, requested_delivery_at=timezone.now())
        OrderItem.objects.create(order=order, product=self.product, name='Cake', quantity=1,
            unit_price=100, delivered_quantity=1 if delivered else 0)
        if delivered:
            post_ledger(self.admin, self.client_record, Decimal('100'), 'delivery', order)
        return order

    def assert_accounting(self, expected):
        self.client_record.refresh_from_db()
        total = LedgerEntry.objects.filter(client=self.client_record).aggregate(total=Sum('amount'))['total'] or Decimal('0')
        self.assertEqual(self.client_record.balance, Decimal(expected))
        self.assertEqual(total, self.client_record.balance)
        for payment in Payment.objects.all():
            allocated = sum(payment.allocations.values_list('amount', flat=True), Decimal('0'))
            self.assertGreaterEqual(allocated, 0)
            self.assertLessEqual(allocated, payment.amount)
            if payment.status != 'confirmed':
                self.assertEqual(allocated, 0)
        for order in Order.objects.all():
            credit = LedgerEntry.objects.filter(order=order, kind='return').aggregate(total=Sum('amount'))['total'] or Decimal('0')
            allocated = PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            self.assertLessEqual(allocated, max(Decimal('0'), order.delivered_total + credit))

    def payment(self, amount='100', order=None, reference=None):
        body = {'client_id': str(self.client_record.pk), 'method': 'kaspi', 'amount': amount, 'reference': reference or str(uuid.uuid4())}
        if order:
            body['order_id'] = str(order.pk)
        response = self.post('payments', body)
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()['id']

    def test_pending_kaspi_customer_cannot_confirm_and_staff_retry_is_single_entry(self):
        self.order()
        payment = self.payment()
        self.assert_accounting('100')
        self.api.force_authenticate(self.customer)
        self.assertEqual(self.post(f'payments/{payment}/confirm', {}).status_code, 403)
        self.assert_accounting('100')
        self.api.force_authenticate(self.cashier)
        key = str(uuid.uuid4())
        first = self.post(f'payments/{payment}/confirm', {}, key)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(self.post(f'payments/{payment}/confirm', {}, key).json(), first.json())
        self.assertEqual(self.post(f'payments/{payment}/confirm', {}).status_code, 409)
        self.assertEqual(LedgerEntry.objects.filter(kind='payment').count(), 1)
        self.assert_accounting('0')

    def test_duplicate_kaspi_reference_cannot_credit_second_pending_payment(self):
        first = self.payment(reference='external-operation')
        second = self.payment()
        self.assertEqual(self.post(f'payments/{first}/confirm', {}).status_code, 200)
        result = self.post(f'payments/{second}/confirm', {'reference': 'external-operation'})
        self.assertEqual(result.status_code, 409, result.content)
        self.assertEqual(Payment.objects.get(pk=second).status, 'pending')
        self.assert_accounting('-100')

    def test_handover_discrepancy_preserves_cash_and_does_not_touch_client_ledger(self):
        self.order()
        CashMovement.objects.create(courier=self.courier, actor=self.admin, amount=150, kind='issue')
        self.api.force_authenticate(self.courier)
        handover = self.post('handovers', {'amount': '120'}).json()['id']
        self.assertEqual(cash_available(self.courier), 30)
        self.api.force_authenticate(self.cashier)
        self.assertEqual(self.post(f'handovers/{handover}/confirm', {'amount': '100'}).status_code, 422)
        self.assertEqual(cash_available(self.courier), 30)
        response = self.post(f'handovers/{handover}/confirm', {'amount': '100', 'reason': 'Counted shortage'})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.post(f'handovers/{handover}/confirm', {'amount': '100'}).status_code, 409)
        self.assertEqual(cash_balance(self.courier), 50)
        self.assertEqual(cash_available(self.courier), 50)
        self.assertEqual(CashboxMovement.objects.aggregate(total=Sum('amount'))['total'], 100)
        self.assertFalse(Payment.objects.exists())
        self.assert_accounting('100')

    def test_cash_change_failure_rolls_back_delivery_then_net_cash_is_booked_once(self):
        order = self.order(False)
        batch = Batch.objects.create(product=self.product, quantity=0, manufactured_at=timezone.now()-timedelta(hours=1), expires_at=timezone.now()+timedelta(days=1))
        Reservation.objects.create(order=order, batch=batch, quantity=1, in_transit=True)
        photo = Photo.objects.create(order=order, uploaded_by=self.courier, purpose='delivery', file='audit.png', content_hash='a'*64, mime='image/png', size=1)
        self.api.force_authenticate(self.courier)
        body = {'version': 1, 'photo_ids': [str(photo.pk)], 'items': [{'product_id': str(self.product.pk), 'quantity': 1}], 'cash_received_amount': '150', 'cash_change_amount': '50'}
        denied = self.post(f'orders/{order.pk}/delivery', body)
        self.assertEqual(denied.status_code, 409, denied.content)
        self.assertTrue(Reservation.objects.filter(order=order).exists())
        self.assertEqual(order.items.get().delivered_quantity, 0)
        self.assertFalse(Payment.objects.exists())
        self.assert_accounting('0')
        CashMovement.objects.create(courier=self.courier, actor=self.admin, amount=50, kind='issue')
        result = self.post(f'orders/{order.pk}/delivery', body)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(self.post(f'orders/{order.pk}/delivery', body).status_code, 409)
        self.assertEqual(Payment.objects.get().amount, 100)
        self.assertEqual(cash_balance(self.courier), 150)
        self.assert_accounting('0')

    def test_return_credit_reallocates_to_other_debt_without_second_payment(self):
        first, second = self.order(), self.order()
        payment = self.payment(order=first)
        self.assertEqual(self.post(f'payments/{payment}/confirm', {}).status_code, 200)
        self.assert_accounting('100')
        request = ReturnRequest.objects.create(order=first, items=[{'product_id': str(self.product.pk), 'quantity': 1}], reason='Damaged', amount=100)
        self.api.force_authenticate(self.admin)
        body = {'decision': 'approve', 'without_collection': True, 'reason': 'Confirmed damage'}
        result = self.post(f'returns/{request.pk}/decide', body)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(self.post(f'returns/{request.pk}/decide', body).status_code, 409)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertFalse(PaymentAllocation.objects.filter(order=first).exists())
        self.assertEqual(PaymentAllocation.objects.get(order=second).amount, 100)
        self.assertEqual(LedgerEntry.objects.filter(kind='return').count(), 1)
        self.assert_accounting('0')

    def test_refund_reserves_advance_and_confirmation_cannot_return_money_twice(self):
        payment = self.payment(amount='150')
        self.assertEqual(self.post(f'payments/{payment}/confirm', {}).status_code, 200)
        self.assert_accounting('-150')
        body = {'client_id': str(self.client_record.pk), 'method': 'kaspi', 'amount': '100', 'reason': 'Customer requested refund'}
        created = self.post('refunds', body)
        self.assertEqual(created.status_code, 201, created.content)
        refund = created.json()['id']
        self.assert_accounting('-150')
        self.assertEqual(self.post('refunds', {**body, 'amount': '51'}).status_code, 409)
        self.api.force_authenticate(self.customer)
        balance = self.api.get('/api/v1/balance').json()
        self.assertEqual(Decimal(balance['advance_amount']), 50)
        self.assertEqual(Decimal(balance['reserved_refund_amount']), 100)
        self.api.force_authenticate(self.cashier)
        self.assertEqual(self.post(f'refunds/{refund}/confirm', {}).status_code, 200)
        self.assertEqual(self.post(f'refunds/{refund}/confirm', {}).status_code, 409)
        self.assertEqual(LedgerEntry.objects.filter(kind='refund').count(), 1)
        self.assert_accounting('-50')
