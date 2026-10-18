"""Export existing remote application data without starting any server."""
import io
import json

from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder

from shop.cloud_snapshot import digest, write_snapshot


class Command(BaseCommand):
    help = 'Export a private application fixture plus referenced Storage photos; not a PostgreSQL backup.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True)
        parser.add_argument('--writers-paused', action='store_true',
                            help='Operator attests writes, uploads/deletes and scheduled jobs are paused.')

    def handle(self, *args, **options):
        if not options['writers_paused']:
            raise CommandError('Pause application writes and jobs, then pass --writers-paused.')
        if connection.vendor != 'postgresql' or settings.STORAGES['default']['BACKEND'] != 'shop.cloud_storage.SupabasePrivateStorage':
            raise CommandError('Requires existing cloud PostgreSQL and Supabase private storage configuration.')
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                fixture = io.StringIO()
                call_command('dumpdata', 'shop', 'auth.group', use_natural_foreign_keys=True,
                             use_base_manager=True, stdout=fixture, verbosity=0)
                migrations = sorted(f'{app}.{name}' for app, name in MigrationRecorder(connection).applied_migrations())
            database = settings.DATABASES['default']
            identity = [database.get(key, '') for key in ('HOST', 'PORT', 'NAME')]
            identity.append(database.get('OPTIONS', {}).get('options', ''))
            metadata = {'migrations': migrations, 'source_database_fingerprint': digest(json.dumps(identity).encode()),
                        'source_storage_fingerprint': digest(settings.SUPABASE_URL.encode()),
                        'writers_paused_attested': True,
                        'scope': 'shop models, auth groups, referenced photos; no sessions or unreferenced objects'}
            report = write_snapshot(options['output'], fixture.getvalue().encode('utf-8'),
                                    lambda name: default_storage.open(name, 'rb'), metadata)
        except Exception:
            raise CommandError('Snapshot export failed; private data and connection details suppressed. No completed archive published.') from None
        self.stdout.write(json.dumps(report, sort_keys=True))
