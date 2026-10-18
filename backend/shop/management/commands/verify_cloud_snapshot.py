import json

from django.core.management.base import BaseCommand, CommandError
from shop.cloud_snapshot import verify_snapshot


class Command(BaseCommand):
    help = 'Offline application snapshot integrity check; does not connect to or restore a database.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('snapshot')

    def handle(self, *args, **options):
        try:
            report = verify_snapshot(options['snapshot'])
        except Exception:
            raise CommandError('Snapshot verification failed; archive contents suppressed.') from None
        self.stdout.write(json.dumps(report, sort_keys=True))
