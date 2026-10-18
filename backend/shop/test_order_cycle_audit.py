"""API acceptance: stock custody, partial delivery, cancellation and exchange."""
import uuid
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import (Batch, Client, DeliveryPoint, LedgerEntry, Order, Photo,
                     Product, Reservation, ReturnRequest, StockMovement, User)


class OrderCycleAuditTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.client = Client.objects.create(name='Cycle', approval_status='active',
            deferred_approved=True, credit_limit=100000, period_start=timezone.localdate())
        self.customer = User.objects.create_user(username='cycle-customer', client=self.client)
        self.admin = User.objects.create_user(username='cycle-admin', role='admin')
        self.courier = User.objects.create_user(username='cycle-courier', role='courier')
        self.point = DeliveryPoint.objects.create(client=self.client, address='Address', recipient='Recipient', phone='+77001112233')
        self.product = Product.objects.create(name='Cake', price=1500)
        now = timezone.now()
        self.early = Batch.objects.create(product=self.product, quantity=3,
            manufactured_at=now-timedelta(hours=1), expires_at=now+timedelta(hours=5))
        self.late = Batch.objects.create(product=self.product, quantity=7,
            manufactured_at=now-timedelta(hours=1), expires_at=now+timedelta(days=2))
        self.api.force_authenticate(self.customer)

    def post(self, path, body, expected=200, key=None):
        response = self.api.post('/api/v1/'+path, body, format='json',
            HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))
        self.assertEqual(response.status_code, expected, response.content)
        return response.json()

    def create(self, quantity=5, **extra):
        return self.post('orders', dict(kind='regular', payment_mode='deferred',
            delivery_point_id=str(self.point.pk), requested_delivery_at=timezone.localtime().replace(hour=15, minute=0).isoformat(),
            items=[dict(product_id=str(self.product.pk), quantity=quantity,
                        expected_unit_price=str(self.product.price))], **extra), 201)

    def transition(self, order, status, **extra):
        return self.post('orders/'+order['id']+'/transition', dict(status=status, version=order['version'], **extra))

    def dispatch(self, order):
        self.api.force_authenticate(self.admin)
        for status in ['accepted', 'preparing', 'ready']:
            order = self.transition(order, status)
        order = self.transition(order, 'ready', courier_id=str(self.courier.pk))
        self.api.force_authenticate(self.courier)
        return self.transition(order, 'out_for_delivery')

    def photo(self, order, user, purpose):
        return str(Photo.objects.create(order_id=order['id'], uploaded_by=user, purpose=purpose,
            file='audit/mock.png', mime='image/png', size=1, content_hash='a'*64).pk)

    def deliver(self, order, quantity, key=None):
        return self.post('orders/'+order['id']+'/delivery', dict(version=order['version'],
            photo_ids=[self.photo(order, self.courier, 'delivery')], reason='Partial accepted',
            items=[dict(product_id=str(self.product.pk), quantity=quantity)]), key=key)

    def test_fefo_partial_receipt_and_exchange_preserve_stock_and_prices(self):
        order = self.create()
        self.assertEqual(list(Reservation.objects.filter(order_id=order['id']).order_by('batch__expires_at').values_list('quantity', flat=True)), [3, 2])
        order = self.dispatch(order)
        self.assertEqual(list(Batch.objects.order_by('expires_at').values_list('quantity', 'reserved')), [(0, 0), (5, 0)])
        self.product.price = 1800
        self.product.save()
        order = self.deliver(order, 3)
        self.assertTrue(order['partial'])
        self.assertEqual(Decimal(order['delivered_amount']), 4500)
        self.client.refresh_from_db()
        self.assertEqual(self.client.reserved_credit, 0)
        self.assertEqual(Reservation.objects.get(order_id=order['id']).quantity, 2)
        self.api.force_authenticate(self.admin)
        goods = dict(reason='Physical warehouse receipt', items=[dict(product_id=str(self.product.pk), quantity=2)])
        key = str(uuid.uuid4())
        self.post('orders/'+order['id']+'/goods-return', goods, key=key)
        self.post('orders/'+order['id']+'/goods-return', goods, key=key)
        self.assertFalse(Reservation.objects.filter(order_id=order['id']).exists())
        self.assertEqual(sum(StockMovement.objects.filter(disposition='quarantine').values_list('quantity', flat=True)), 2)
        self.assertEqual(sum(Batch.objects.values_list('quantity', flat=True)), 5)
        self.api.force_authenticate(self.customer)
        body = dict(order_id=order['id'], kind='exchange', reason='Damaged',
            photo_ids=[self.photo(order, self.customer, 'exchange')],
            items=[dict(product_id=str(self.product.pk), quantity=1)])
        ret = self.post('returns', body, 201)
        self.api.force_authenticate(self.admin)
        self.post('returns/'+ret['id']+'/decide', dict(decision='approve', reason='Accepted'))
        self.assertFalse(ReturnRequest.objects.get(pk=ret['id']).credited)
        self.post('returns/'+ret['id']+'/receive', dict(reason='Received', photo_ids=[self.photo(order, self.admin, 'exchange')]))
        self.assertTrue(ReturnRequest.objects.get(pk=ret['id']).credited)
        self.assertEqual(LedgerEntry.objects.get(kind='return').amount, -1500)
        self.api.force_authenticate(self.customer)
        replacement = self.create(1, exchange_id=ret['id'])
        self.assertEqual(replacement['exchange_id'], ret['id'])
        self.assertEqual(Decimal(replacement['total_amount']), 1800)
        replacement = self.dispatch(replacement)
        replacement = self.deliver(replacement, 1)
        self.assertEqual(replacement['status'], 'delivered')
        self.assertEqual(Order.objects.get(pk=order['id']).items.get().unit_price, 1500)
        self.assertEqual(sum(Batch.objects.values_list('quantity', flat=True)), 4)
        self.client.refresh_from_db()
        self.assertEqual(self.client.balance, 4800)
        self.assertEqual(self.client.reserved_credit, 0)

    def test_cancel_before_dispatch_releases_both_fefo_reserves_once(self):
        order = self.create()
        self.api.force_authenticate(self.admin)
        order = self.transition(order, 'accepted')
        body = dict(status='cancelled', reason='Cancelled', version=order['version'])
        key = str(uuid.uuid4())
        self.post('orders/'+order['id']+'/transition', body, key=key)
        self.post('orders/'+order['id']+'/transition', body, key=key)
        self.assertEqual(sum(Batch.objects.values_list('quantity', flat=True)), 10)
        self.assertEqual(sum(Batch.objects.values_list('reserved', flat=True)), 0)
        self.assertFalse(Reservation.objects.exists())
        self.assertFalse(LedgerEntry.objects.exists())
        self.client.refresh_from_db()
        self.assertEqual(self.client.reserved_credit, 0)

    def test_failed_delivery_retry_does_not_dispatch_stock_twice(self):
        order = self.dispatch(self.create())
        order = self.post('orders/'+order['id']+'/delivery-failed', dict(reason='Client absent', version=order['version']))
        self.assertFalse(LedgerEntry.objects.exists())
        self.assertEqual(sum(Reservation.objects.values_list('quantity', flat=True)), 5)
        order = self.transition(order, 'out_for_delivery')
        self.assertEqual(sum(Batch.objects.values_list('quantity', flat=True)), 5)
        self.assertEqual(StockMovement.objects.filter(disposition='courier').count(), 2)
        order = self.deliver(order, 5)
        self.assertEqual(Order.objects.get(pk=order['id']).attempts.count(), 2)
        self.assertEqual(LedgerEntry.objects.filter(kind='delivery').count(), 1)

    def test_pending_return_reserves_delivered_quantity(self):
        order = self.deliver(self.dispatch(self.create(2)), 2)
        self.api.force_authenticate(self.customer)
        body = dict(order_id=order['id'], reason='Return',
            photo_ids=[self.photo(order, self.customer, 'return')],
            items=[dict(product_id=str(self.product.pk), quantity=2)])
        ret = self.post('returns', body, 201)
        response = self.post('returns', body, 409)
        self.assertEqual(response['code'], 'RETURN_EXCEEDS_DELIVERED')
        self.api.force_authenticate(self.admin)
        self.post('returns/'+ret['id']+'/decide', dict(decision='reject', reason='Not eligible'))
        self.api.force_authenticate(self.customer)
        self.post('returns', body, 201)

    def test_failed_delivery_full_goods_receipt_allows_terminal_cancellation(self):
        order = self.dispatch(self.create())
        self.api.force_authenticate(self.customer)
        other = self.create(1)
        self.api.force_authenticate(self.courier)
        order = self.post('orders/'+order['id']+'/delivery-failed', dict(reason='Client refused', version=order['version']))
        self.api.force_authenticate(self.admin)
        self.post('orders/'+order['id']+'/goods-return', dict(reason='All goods physically received',
            items=[dict(product_id=str(self.product.pk), quantity=5)]))
        self.assertFalse(Reservation.objects.filter(order_id=order['id']).exists())
        body = dict(status='cancelled', version=order['version'], reason='No goods remain in courier custody')
        key = str(uuid.uuid4())
        self.post('orders/'+order['id']+'/transition', body, key=key)
        self.post('orders/'+order['id']+'/transition', body, key=key)
        self.post('orders/'+order['id']+'/transition', body, 409)
        self.client.refresh_from_db()
        self.assertEqual(self.client.reserved_credit, 1500)
        self.assertEqual(Reservation.objects.get(order_id=other['id']).quantity, 1)
        self.assertFalse(LedgerEntry.objects.exists())

    def test_rejected_partial_delivery_rolls_back_stock_and_charge(self):
        order = self.dispatch(self.create())
        body = dict(version=order['version'],
            photo_ids=[self.photo(order, self.courier, 'delivery')],
            items=[dict(product_id=str(self.product.pk), quantity=3)])
        self.post('orders/'+order['id']+'/delivery', body, 422)
        self.assertEqual(sum(Reservation.objects.values_list('quantity', flat=True)), 5)
        self.assertFalse(LedgerEntry.objects.exists())
        self.assertFalse(StockMovement.objects.filter(disposition='delivery').exists())
        persisted = Order.objects.get(pk=order['id'])
        self.assertEqual(persisted.status, 'out_for_delivery')
        self.assertEqual(persisted.items.get().delivered_quantity, 0)
        self.client.refresh_from_db()
        self.assertEqual(self.client.reserved_credit, 7500)

    def test_delivery_replay_does_not_duplicate_charge_or_stock(self):
        order = self.dispatch(self.create())
        body = dict(version=order['version'],
            photo_ids=[self.photo(order, self.courier, 'delivery')],
            items=[dict(product_id=str(self.product.pk), quantity=5)])
        key = str(uuid.uuid4())
        first = self.post('orders/'+order['id']+'/delivery', body, key=key)
        self.assertEqual(first, self.post('orders/'+order['id']+'/delivery', body, key=key))
        self.post('orders/'+order['id']+'/delivery', body, 409)
        self.assertEqual(LedgerEntry.objects.filter(kind='delivery').count(), 1)
        self.assertEqual(StockMovement.objects.filter(disposition='delivery').count(), 1)
        self.assertEqual(sum(Batch.objects.values_list('quantity', flat=True)), 5)
        self.assertFalse(Reservation.objects.exists())

    def test_failed_delivery_cannot_retry_after_goods_leave_courier(self):
        order = self.dispatch(self.create())
        order = self.post('orders/'+order['id']+'/delivery-failed', dict(reason='Refused', version=order['version']))
        self.api.force_authenticate(self.admin)
        self.post('orders/'+order['id']+'/goods-return', dict(reason='Partial physical receipt',
            items=[dict(product_id=str(self.product.pk), quantity=2)]))
        self.post('orders/'+order['id']+'/transition', dict(status='cancelled', version=order['version'], reason='Still has goods'), 409)
        self.api.force_authenticate(self.courier)
        self.post('orders/'+order['id']+'/transition', dict(status='out_for_delivery', version=order['version']), 409)
        self.assertEqual(Order.objects.get(pk=order['id']).status, 'delivery_failed')
        self.client.refresh_from_db()
        self.assertEqual(self.client.reserved_credit, 7500)
