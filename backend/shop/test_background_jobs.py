"""One-shot scheduler behavior; all business jobs run against the test database."""
import io
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command, get_commands
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from .models import Client, DeliveryPoint, LedgerEntry, Notification, Order, Period, User, WeeklyReport


class BackgroundJobsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='scheduler', role='accountant')
        today = timezone.localdate()
        self.org = Client.objects.create(name='Scheduler', balance=100, period_start=today-timedelta(days=14), period_days=7)
        point = DeliveryPoint.objects.create(client=self.org, address='Test', recipient='Test', phone='Test')
        self.order = Order.objects.create(client=self.org, delivery_point=point,
            address_snapshot='{}', kind='regular', status='submitted', payment_mode='cash', total=0,
            requested_delivery_at=timezone.now(), reservation_expires_at=timezone.now()-timedelta(seconds=1))
        delivered = Order.objects.create(client=self.org, delivery_point=point,
            address_snapshot='{}', kind='regular', status='delivered', total=100, delivered_total=100,
            requested_delivery_at=timezone.now()-timedelta(days=10))
        period = Period.objects.create(client=self.org, start=today-timedelta(days=14), end_exclusive=today-timedelta(days=7))
        entry = LedgerEntry.objects.create(client=self.org, order=delivered, kind='delivery', amount=100,
            actor=self.staff, period=period, reference='scheduler-test')
        LedgerEntry.objects.filter(pk=entry.pk).update(created_at=timezone.now()-timedelta(days=10))
        self.output = io.StringIO()

    def run_jobs(self):
        call_command('run_background_jobs', stdout=self.output, stderr=self.output)

    def test_scheduler_command_is_available(self):
        self.assertIn('run_background_jobs', get_commands())

    def test_two_runs_expire_order_and_preserve_period_and_report_snapshots(self):
        self.run_jobs()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled')
        version = self.order.version
        periods = list(Period.objects.filter(closed_at__isnull=False).values('id', 'snapshot', 'closed_at'))
        reports = list(WeeklyReport.objects.values('id', 'payload'))
        self.assertTrue(periods)
        self.assertTrue(reports)
        notice_ids = list(Notification.objects.filter(message='debt.overdue').values_list('id', flat=True))
        self.assertEqual(len(notice_ids), 1)
        self.run_jobs()
        self.order.refresh_from_db()
        self.assertEqual(self.order.version, version)
        self.assertEqual(list(Period.objects.filter(closed_at__isnull=False).values('id', 'snapshot', 'closed_at')), periods)
        self.assertEqual(list(WeeklyReport.objects.values('id', 'payload')), reports)
        self.assertEqual(list(Notification.objects.filter(message='debt.overdue').values_list('id', flat=True)), notice_ids)
        self.assertIn('status=completed', self.output.getvalue())

    def test_report_failure_rolls_back_earlier_jobs_and_returns_error(self):
        with patch('shop.management.commands.generate_weekly_reports.report', side_effect=RuntimeError('provider unavailable')):
            with self.assertRaises(CommandError):
                self.run_jobs()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertFalse(Period.objects.filter(closed_at__isnull=False).exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(WeeklyReport.objects.exists())
        self.assertIn('status=failed', self.output.getvalue())

    def test_contended_lock_skips_all_jobs(self):
        with patch('shop.management.commands.run_background_jobs.acquire_job_lock', return_value=False):
            self.run_jobs()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')
        self.assertFalse(WeeklyReport.objects.exists())
        self.assertIn('status=skipped', self.output.getvalue())

    def test_no_active_staff_fails_before_mutation(self):
        self.staff.is_active = False
        self.staff.save()
        with self.assertRaises(CommandError):
            self.run_jobs()
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'submitted')

    def test_individual_financial_jobs_reject_inactive_staff(self):
        self.staff.is_active = False
        self.staff.save()
        for name in ('close_periods', 'generate_weekly_reports'):
            with self.subTest(command=name), self.assertRaises(CommandError):
                call_command(name, stdout=self.output, stderr=self.output)
