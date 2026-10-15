from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from .models import Client, User, Period, LedgerEntry
from .services import post_ledger


class PeriodConfigurationBoundaryTests(TestCase):
    def test_first_delivery_at_new_boundary_uses_pending_period_without_worker(self):
        actor=User.objects.create_user(username='+77018888881',password='BoundaryLocalOnly!',role='admin')
        client=Client.objects.create(name='Period boundary',approval_status='active',period_start=date(2026,10,13),
            period_days=14,pending_period_days=7,period_change_at=date(2026,10,27),balance='1500.00')
        old=Period.objects.create(client=client,start=date(2026,10,13),end_exclusive=date(2026,10,27))
        previous=LedgerEntry.objects.create(client=client,period=old,actor=actor,kind='delivery',amount='1500.00',reference='boundary-before')
        with patch('django.utils.timezone.localdate',return_value=date(2026,10,27)):
            entry=post_ledger(actor,client,Decimal('1500.00'),'delivery',reference='boundary-after')
        self.assertEqual(entry.period.start,date(2026,10,27))
        self.assertEqual(entry.period.end_exclusive,date(2026,11,3))
        client.refresh_from_db()
        self.assertEqual(client.period_days,7)
        old.refresh_from_db()
        previous.refresh_from_db()
        self.assertEqual(old.end_exclusive,date(2026,10,27))
        self.assertEqual(previous.period_id,old.pk)
