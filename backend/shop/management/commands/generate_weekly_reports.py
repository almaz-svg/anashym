from datetime import date,timedelta
from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from django.utils import timezone
from shop.models import WeeklyReport,User,LedgerEntry
from shop.routes import report

class Command(BaseCommand):
    help=('Catch up all completed business weeks since the first ledger entry; '
          'existing snapshots are immutable. Empty demos receive the previous week.')

    def add_arguments(self,parser):
        parser.add_argument('--start',help=(
            'YYYY-MM-DD: snapshot only the Monday-Sunday week containing this date. '
            'For compatibility this explicit mode also permits an unfinished week; '
            'it freezes the data available now and later runs never replace it.'))

    def handle(self,*args,**options):
        if options.get('start'):
            try:day=date.fromisoformat(options['start'])
            except ValueError as exc:raise CommandError('--start must use YYYY-MM-DD') from exc
            start=day-timedelta(days=day.weekday())
            stop=start+timedelta(days=7)
        else:
            today=timezone.localdate()
            stop=today-timedelta(days=today.weekday())
            start=stop-timedelta(days=7)
            first=LedgerEntry.objects.order_by('created_at').values_list('created_at',flat=True).first()
            if first:
                first_day=timezone.localtime(first).date()
                start=min(start,first_day-timedelta(days=first_day.weekday()))
        actor=User.objects.filter(role='accountant').first() or User.objects.filter(role='admin').first()
        if not actor: self.stderr.write('No authorized staff account'); return
        while start<stop:
            end=start+timedelta(days=7)
            with transaction.atomic():
                # The unique start serializes competing workers. This placeholder
                # is never committed until its full report has been generated.
                obj,created=WeeklyReport.objects.get_or_create(start=start,defaults={'end_exclusive':end,'payload':{}})
                if created:
                    payload,_=report(actor,{'from':start.isoformat(),'to':(end-timedelta(days=1)).isoformat()})
                    obj.payload=payload
                    obj.save(update_fields=['payload'])
            self.stdout.write(f'Weekly report {obj.pk}: {"created" if created else "already exists"}')
            start=end
