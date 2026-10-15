"""Weekly archive catch-up, immutability, and failed-generation regression tests."""
import io
from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch
from django.core.management import call_command
from django.test import TestCase
from .models import Client, LedgerEntry, User, WeeklyReport


class WeeklyGenerationTests(TestCase):
    today = date(2026, 10, 14)

    def setUp(self):
        self.actor = User.objects.create_user(username='weekly-review', role='accountant')
        self.client = Client.objects.create(name='Weekly review')
        self.output = io.StringIO()

    def run_command(self, **options):
        with patch('shop.management.commands.generate_weekly_reports.timezone.localdate', return_value=self.today):
            call_command('generate_weekly_reports', stdout=self.output, **options)

    def first_entry(self):
        entry = LedgerEntry.objects.create(client=self.client, actor=self.actor,
            kind='payment', amount='-100', reference='weekly-first')
        # Sunday in UTC is already Monday in the application's business timezone.
        LedgerEntry.objects.filter(pk=entry.pk).update(created_at=datetime(2026, 9, 6, 20, tzinfo=dt_timezone.utc))

    @patch('shop.management.commands.generate_weekly_reports.report')
    def test_automatic_run_catches_up_every_completed_business_week(self, report):
        self.first_entry()
        report.side_effect = lambda actor, params: ({'from': params['from'], 'to': params['to'], 'items': []}, 200)
        self.run_command()
        self.assertEqual(list(WeeklyReport.objects.order_by('start').values_list('start', flat=True)),
            [date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21), date(2026, 9, 28), date(2026, 10, 5)])
        self.assertEqual(report.call_count, 5)
        self.assertFalse(WeeklyReport.objects.filter(start=date(2026, 10, 12)).exists())

    @patch('shop.management.commands.generate_weekly_reports.report', return_value=({'unexpected': True}, 200))
    def test_existing_snapshot_is_neither_calculated_nor_replaced(self, report):
        original = {'sentinel': 'immutable snapshot'}
        archive = WeeklyReport.objects.create(start=date(2026, 10, 5), end_exclusive=date(2026, 10, 12), payload=original)
        self.run_command()
        self.run_command()
        report.assert_not_called()
        archive.refresh_from_db()
        self.assertEqual(archive.payload, original)
        self.assertEqual(WeeklyReport.objects.count(), 1)

    @patch('shop.management.commands.generate_weekly_reports.report', return_value=({'items': []}, 200))
    def test_empty_demo_gets_previous_completed_week(self, report):
        self.run_command()
        self.assertEqual(list(WeeklyReport.objects.values_list('start', flat=True)), [date(2026, 10, 5)])
        report.assert_called_once()

    @patch('shop.management.commands.generate_weekly_reports.report', return_value=({'manual': True}, 200))
    def test_explicit_start_only_snapshots_its_containing_week(self, report):
        self.first_entry()
        self.run_command(start='2026-10-14')
        self.assertEqual(list(WeeklyReport.objects.values_list('start', flat=True)), [date(2026, 10, 12)])
        self.run_command(start='2026-10-14')
        report.assert_called_once()

    @patch('shop.management.commands.generate_weekly_reports.report', side_effect=RuntimeError('Generation failed'))
    def test_failed_generation_does_not_leave_empty_archive(self, report):
        with self.assertRaisesRegex(RuntimeError, 'Generation failed'):
            self.run_command()
        self.assertEqual(WeeklyReport.objects.count(), 0)
