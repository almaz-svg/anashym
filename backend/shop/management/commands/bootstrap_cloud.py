"""Prepare the existing cloud database without copying local customer data."""
import io
import json
import os
from urllib.error import HTTPError
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from shop.cloud_storage import SupabasePrivateStorage


class Command(BaseCommand):
    help = 'Prepare the cloud schema and private storage; demo seed requires CLOUD_SEED_DEMO=1'

    def handle(self, *args, **options):
        if not hasattr(settings, 'SUPABASE_STORAGE_KEY') or not settings.SUPABASE_STORAGE_KEY:
            raise CommandError('Cloud storage configuration is required')
        if connection.settings_dict.get('OPTIONS', {}).get('options') != '-c search_path=bakery':
            raise CommandError('Refusing to initialize a non-cloud database')
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(734129861)')
                cursor.execute('CREATE SCHEMA IF NOT EXISTS bakery')
                cursor.execute('REVOKE ALL ON SCHEMA bakery FROM PUBLIC')
            call_command('migrate', interactive=False, verbosity=0)
            # Production deployments must not recreate demo accounts or inventory.
            if os.getenv('CLOUD_SEED_DEMO') == '1':
                call_command('seed_demo', stdout=io.StringIO())
        storage = SupabasePrivateStorage()
        bucket = settings.SUPABASE_MEDIA_BUCKET
        try:
            with storage._request('bucket/' + bucket) as response:
                existing = json.loads(response.read())
            if existing.get('public'):
                raise CommandError('The photo bucket must be private')
        except HTTPError as exc:
            if exc.code not in (400, 404):
                raise
            with storage._request('bucket', 'POST', json.dumps({
                'id': bucket, 'name': bucket, 'public': False,
                'file_size_limit': 10485760,
                'allowed_mime_types': ['image/jpeg', 'image/png', 'image/webp'],
            }).encode(), 'application/json'):
                pass
        self.stdout.write('Cloud schema and private storage are ready.')
        if os.getenv('CLOUD_SEED_DEMO') == '1':
            self.stdout.write('Demo seed requested through CLOUD_SEED_DEMO=1 and completed.')
