from datetime import timedelta
from django.db import migrations
from django.utils import timezone

def backfill(apps,schema_editor):
    Ledger=apps.get_model('shop','LedgerEntry'); Period=apps.get_model('shop','Period')
    for entry in Ledger.objects.filter(period__isnull=True).select_related('client').iterator():
        c=entry.client; day=timezone.localtime(entry.created_at).date(); start=c.period_start+timedelta(days=max(0,(day-c.period_start).days//c.period_days)*c.period_days)
        period,_=Period.objects.get_or_create(client=c,start=start,defaults={'end_exclusive':start+timedelta(days=c.period_days)})
        Ledger.objects.filter(pk=entry.pk).update(period=period)

class Migration(migrations.Migration):
    dependencies=[('shop','0011_client_pending_period_days_client_period_change_at_and_more')]
    operations=[migrations.RunPython(backfill,migrations.RunPython.noop)]
