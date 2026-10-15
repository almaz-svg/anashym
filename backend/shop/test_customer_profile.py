"""Customer profile totals distinguish current obligations from dated cash flows."""
import uuid
from datetime import datetime, timedelta, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Client, DeliveryPoint, LedgerEntry, Order, Payment, PaymentAllocation, Period, User


ALMATY = ZoneInfo('Asia/Almaty')


class CustomerProfileTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.customer = Client.objects.create(
            name='Coffee point', category='other', category_other='Bakery', description='Daily pastry',
            approval_status='active', preferred_payment_mode='deferred', credit_limit='20000.00',
            expected_order_quantity=12, expected_order_frequency='Every weekday', period_days=7,
        )
        self.user = User.objects.create_user(username='+77010000031', first_name='Aida', client=self.customer)
        self.other = Client.objects.create(name='Private second client', approval_status='active', balance='99999.00')
        self.admin = User.objects.create_user(username='profile-admin', role='admin')
        self.api.force_authenticate(self.user)
        self.start = datetime(2026, 10, 12, tzinfo=ALMATY)
        self.end = datetime(2026, 10, 19, tzinfo=ALMATY)
        self.dates = {'from': '2026-10-12', 'to': '2026-10-18'}

    def order(self, amount, when, client=None, period=None):
        client = client or self.customer
        point = DeliveryPoint.objects.create(client=client, address='Test address', recipient='Recipient', phone='+77010000000')
        order = Order.objects.create(
            client=client, delivery_point=point, address_snapshot='{}', kind='regular', status='delivered',
            total=amount, delivered_total=amount, requested_delivery_at=when + timedelta(days=30),
        )
        self.entry(order, amount, 'delivery', when, period=period)
        return order

    def entry(self, order, amount, kind, when, period=None):
        entry = LedgerEntry.objects.create(
            client=order.client, order=order, amount=amount, kind=kind, actor=self.admin,
            reference=str(uuid.uuid4()), period=period,
        )
        LedgerEntry.objects.filter(pk=entry.pk).update(created_at=when)
        return entry

    def payment(self, order, amount, when, status='confirmed'):
        payment = Payment.objects.create(
            client=order.client, order=order, method='kaspi', amount=amount, status=status,
            actor=self.admin, confirmed_at=when if status == 'confirmed' else None,
        )
        PaymentAllocation.objects.create(payment=payment, order=order, amount=amount)
        if status == 'confirmed':
            self.entry(order, -Decimal(str(amount)), 'payment', when)
        return payment

    def profile(self, params=None):
        response = self.api.get('/api/v1/profile', self.dates if params is None else params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_profile_only_exposes_current_customer_identity(self):
        payload = self.profile()
        self.assertEqual(payload['profile'], {
            'name': 'Coffee point', 'contact_name': 'Aida', 'phone': '+77010000031',
            'category': 'other', 'category_other': 'Bakery', 'description': 'Daily pastry',
            'approval_status': 'active', 'deferred_approved': False, 'archived': False, 'preferred_payment_mode': 'deferred',
            'expected_order_quantity': 12, 'expected_order_frequency': 'Every weekday',
            'period_days': 7, 'credit_limit_amount': '20000.00',
        })
        self.assertEqual(payload['currency'], 'KZT')
        self.assertNotIn('Private second client', str(payload))
        response = self.api.get('/api/v1/profile', {**self.dates, 'client_id': str(self.other.pk)})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn('99999', response.content.decode())

    def test_profile_rejects_staff_and_anonymous_requests(self):
        for role in ('admin', 'accountant', 'cashier', 'courier'):
            with self.subTest(role=role):
                staff = User.objects.create_user(username='profile-' + role + '-scope', role=role, client=self.other)
                self.api.force_authenticate(staff)
                self.assertEqual(self.api.get('/api/v1/profile').status_code, 403)
        self.api.force_authenticate(None)
        self.assertEqual(self.api.get('/api/v1/profile').status_code, 401)

    def test_unapproved_customer_can_view_profile_without_unlocking_catalog(self):
        for status in ('pending', 'rejected'):
            with self.subTest(status=status):
                Client.objects.filter(pk=self.customer.pk).update(approval_status=status)
                self.user = User.objects.get(pk=self.user.pk)
                self.api.force_authenticate(self.user)
                self.assertEqual(self.profile()['profile']['approval_status'], status)
                self.assertEqual(self.api.get('/api/v1/catalog', {'delivery_date': '2026-10-15'}).status_code, 403)

    def test_default_week_uses_almaty_date_even_before_utc_monday(self):
        now = datetime(2026, 10, 11, 20, tzinfo=datetime_timezone.utc)
        with timezone.override('UTC'), patch('django.utils.timezone.now', return_value=now):
            payload = self.profile({})
        self.assertEqual((payload['from'], payload['to']), ('2026-10-12', '2026-10-18'))
        self.assertEqual(datetime.fromisoformat(payload['generated_at']), now)

    def test_invalid_or_unbounded_periods_are_rejected(self):
        for params in (
            {'from': '2026-10-12'}, {'to': '2026-10-18'},
            {'from': '', 'to': '2026-10-18'},
            {'from': '2026-02-30', 'to': '2026-10-18'},
            {'from': '20261012', 'to': '2026-10-18'},
            {'from': '2026-10-18', 'to': '2026-10-12'},
            {'from': '2025-10-12', 'to': '2026-10-13'},
        ):
            with self.subTest(params=params):
                self.assertEqual(self.api.get('/api/v1/profile', params).status_code, 422)
        self.assertEqual(self.api.get('/api/v1/profile', {'from': '2025-10-13', 'to': '2026-10-13'}).status_code, 200)

    def test_period_includes_local_midnight_and_sunday_but_excludes_other_clients(self):
        self.order('700.00', self.start - timedelta(microseconds=1))
        self.order('100.00', self.start)
        self.order('200.00', self.end - timedelta(microseconds=1))
        self.order('800.00', self.end)
        self.order('999.00', self.start, client=self.other)
        with timezone.override('UTC'):
            payload = self.profile()
        self.assertEqual(payload['period']['delivered_amount'], '300.00')
        self.assertEqual(payload['period']['outstanding_amount'], '300.00')

    def test_week_outstanding_excludes_old_debt_and_applies_later_payments_and_returns(self):
        old = self.order('10000.00', self.start - timedelta(days=1))
        current = self.order('1000.00', self.start + timedelta(days=1))
        self.payment(old, 100, self.start + timedelta(days=2))
        self.payment(current, 300, self.end + timedelta(days=1))
        self.entry(current, '-200.00', 'return', self.end + timedelta(days=2))
        # A pending allocation must not pretend the customer's debt was paid.
        self.payment(current, 450, self.start + timedelta(days=3), status='pending')
        Client.objects.filter(pk=self.customer.pk).update(balance='10400.00')
        self.user = User.objects.get(pk=self.user.pk)
        self.api.force_authenticate(self.user)
        payload = self.profile()
        self.assertEqual(payload['balance']['debt_amount'], '10400.00')
        self.assertEqual(payload['balance']['unconfirmed_payment_amount'], '450.00')
        self.assertEqual(payload['period'], {
            'delivered_amount': '1000.00', 'return_credit_amount': '0.00', 'turnover_amount': '1000.00',
            'paid_amount': '100.00', 'refund_amount': '0.00', 'outstanding_amount': '500.00',
        })

    def test_period_cash_flows_keep_returns_and_refunds_separate_from_outstanding(self):
        order = self.order('1000.00', self.start)
        self.payment(order, 700, self.start + timedelta(days=1))
        self.entry(order, '-100.00', 'return', self.start + timedelta(days=2))
        self.entry(order, '25.00', 'refund', self.start + timedelta(days=3))
        self.assertEqual(self.profile()['period'], {
            'delivered_amount': '1000.00', 'return_credit_amount': '100.00', 'turnover_amount': '900.00',
            'paid_amount': '700.00', 'refund_amount': '25.00', 'outstanding_amount': '200.00',
        })

    def test_balance_shows_advance_and_only_own_pending_payments(self):
        Client.objects.filter(pk=self.customer.pk).update(balance='-123.45')
        self.user = User.objects.get(pk=self.user.pk)
        self.api.force_authenticate(self.user)
        for client, status, amount in (
            (self.customer, 'pending', '40.00'), (self.customer, 'pending', '60.00'),
            (self.customer, 'confirmed', '200.00'), (self.customer, 'rejected', '300.00'),
            (self.other, 'pending', '999.00'),
        ):
            Payment.objects.create(client=client, status=status, amount=amount, method='cash', actor=self.admin)
        payload = self.profile()
        self.assertEqual(payload['balance'], {
            'debt_amount': '0.00', 'advance_amount': '123.45', 'overdue_amount': '0.00',
            'unconfirmed_payment_amount': '100.00', 'reserved_refund_amount': '0.00',
        })

    def test_overdue_uses_current_obligations_ignoring_stale_recorded_overdue(self):
        period = Period.objects.create(client=self.customer, start='2026-10-05', end_exclusive='2026-10-12')
        order = self.order('1000.00', self.start - timedelta(days=1), period=period)
        self.payment(order, 300, self.start + timedelta(days=1))
        self.entry(order, '-200.00', 'return', self.start + timedelta(days=2))
        with patch('django.utils.timezone.now', return_value=self.end):
            for recorded, expected in (('100.00', '500.00'), ('800.00', '500.00')):
                with self.subTest(recorded=recorded):
                    Client.objects.filter(pk=self.customer.pk).update(overdue=recorded)
                    self.user = User.objects.get(pk=self.user.pk)
                    self.api.force_authenticate(self.user)
                    self.assertEqual(self.profile()['balance']['overdue_amount'], expected)
