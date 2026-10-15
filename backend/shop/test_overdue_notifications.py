from datetime import timedelta
from decimal import Decimal
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from .models import Client, DeliveryPoint, LedgerEntry, Notification, Order, Payment, PaymentAllocation, Period, User


class OverdueNotificationTests(TestCase):
    def setUp(self):
        today = timezone.localdate()
        self.org = Client.objects.create(name='Merimi', approval_status='active', balance='500.00', overdue='999.00')
        self.member = User.objects.create_user(username='reminder-member', client=self.org)
        self.admin = User.objects.create_user(username='reminder-admin', role='admin')
        self.other = User.objects.create_user(username='reminder-other', client=Client.objects.create(name='Other'))
        point = DeliveryPoint.objects.create(client=self.org, address='Test', recipient='Test', phone='+77000000001')
        self.order = Order.objects.create(client=self.org, delivery_point=point, address_snapshot='{}', kind='regular', status='delivered', total=500, delivered_total=500, requested_delivery_at=timezone.now())
        period = Period.objects.create(client=self.org, start=today-timedelta(days=8), end_exclusive=today-timedelta(days=1))
        LedgerEntry.objects.create(client=self.org, order=self.order, kind='delivery', amount=500, actor=self.admin, reference='overdue-test', period=period)

    def test_one_daily_reminder_uses_derived_amount_and_is_scoped(self):
        call_command('notify_overdue', verbosity=0)
        call_command('notify_overdue', verbosity=0)
        self.assertEqual(Notification.objects.filter(message='debt.overdue').count(), 2)
        notice = Notification.objects.get(user=self.member)
        self.assertEqual(notice.payload['overdue_amount'], '500.00')
        self.assertFalse(Notification.objects.filter(user=self.other).exists())

    def test_paid_debt_does_not_generate_reminder_from_stale_cached_overdue(self):
        payment = Payment.objects.create(client=self.org, order=self.order, method='kaspi', amount=500, status='confirmed', actor=self.admin)
        PaymentAllocation.objects.create(payment=payment, order=self.order, amount=500)
        call_command('notify_overdue', verbosity=0)
        self.assertFalse(Notification.objects.exists())

    def test_inactive_users_do_not_receive_reminders(self):
        self.member.is_active = False
        self.member.save(update_fields=['is_active'])
        call_command('notify_overdue', verbosity=0)
        self.assertFalse(Notification.objects.filter(user=self.member).exists())

    def test_due_date_is_exclusive_period_end_not_order_date(self):
        Period.objects.filter(client=self.org).update(end_exclusive=timezone.localdate()+timedelta(days=1))
        call_command('notify_overdue', verbosity=0)
        self.assertFalse(Notification.objects.exists())
