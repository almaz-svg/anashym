"""Finite cron entry point; transaction locks also work with PostgreSQL poolers."""
from time import monotonic

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from shop.models import User


JOBS = ('expire_reservations', 'close_periods', 'notify_overdue', 'generate_weekly_reports')
# A stable application-specific key, shared by every deployment of this scheduler.
LOCK_KEY = 0x42414B455259


def acquire_job_lock():
    if connection.vendor == 'sqlite':
        # SQLite is supported for isolated tests, not concurrent cron workers.
        return True
    if connection.vendor != 'postgresql':
        raise CommandError('Background jobs require PostgreSQL (SQLite is for tests only)')
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [LOCK_KEY])
        return cursor.fetchone()[0]


class Command(BaseCommand):
    help = 'Run periodic business jobs once and exit with a transaction lock'

    def handle(self, *args, **options):
        started = monotonic()
        job = 'preflight'
        try:
            with transaction.atomic():
                if not acquire_job_lock():
                    self.stdout.write(f'{timezone.now().isoformat()} status=skipped reason=already_running')
                    return
                if not User.objects.filter(is_active=True, role__in=['admin', 'accountant']).exists():
                    raise CommandError('An active admin or accountant is required')
                for job in JOBS:
                    self.stdout.write(f'{timezone.now().isoformat()} job={job} status=started')
                    call_command(job, stdout=self.stdout, stderr=self.stderr, verbosity=options['verbosity'])
                    self.stdout.write(f'{timezone.now().isoformat()} job={job} status=executed pending_commit=true')
        except Exception as exc:
            self.stderr.write(f'{timezone.now().isoformat()} job={job} status=failed error_type={type(exc).__name__}')
            # Avoid copying potentially sensitive database/provider messages into cron logs.
            raise CommandError(f'Background jobs failed at {job}; transaction rolled back') from exc
        self.stdout.write(f'{timezone.now().isoformat()} status=completed elapsed_seconds={monotonic()-started:.3f}')
