"""Read-only, secret-free deployment checks; not a backup or activation tool."""
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from shop.models import User


def build_report(users, config):
    roles = dict.fromkeys(('admin', 'cashier', 'courier'), 0)
    demo_names = {f'+7701000000{number}' for number in range(1, 6)}
    active_demo = 0
    for user in users:
        if not user['is_active']:
            continue
        if user['role'] in roles:
            roles[user['role']] += 1
        active_demo += user['username'] in demo_names
    database = config.DATABASES.get('default', {})
    options = database.get('OPTIONS', {})
    hosts = getattr(config, 'ALLOWED_HOSTS', [])
    checks = {
        'debug_disabled': not config.DEBUG,
        'strong_secret_configured': len(config.SECRET_KEY) >= 50 and not config.SECRET_KEY.startswith('django-insecure-'),
        'hosts_restricted': bool(hosts) and '*' not in hosts,
        'secure_cookies': bool(config.SESSION_COOKIE_SECURE and config.CSRF_COOKIE_SECURE),
        'postgres_tls_configured': database.get('ENGINE') == 'django.db.backends.postgresql'
            and options.get('sslmode') in {'require', 'verify-ca', 'verify-full'},
        'bakery_schema_configured': options.get('options') == '-c search_path=bakery',
        'private_storage_configured': getattr(config, 'STORAGES', {}).get('default', {}).get('BACKEND')
            == 'shop.cloud_storage.SupabasePrivateStorage'
            and bool(getattr(config, 'SUPABASE_URL', '').startswith('https://'))
            and bool(getattr(config, 'SUPABASE_STORAGE_KEY', ''))
            and getattr(config, 'SUPABASE_MEDIA_BUCKET', '') == 'bakery-private-media',
        'known_demo_accounts_disabled': active_demo == 0,
        'required_roles_active': all(roles.values()),
    }
    return {
        'checks_passed': all(checks.values()), 'checks': checks,
        'active_roles': roles, 'active_known_demo_accounts': active_demo,
        'not_verified': ['password_strength_or_activation', 'unknown_demo_accounts',
                         'storage_connectivity_and_bucket_privacy', 'backup_restore_drill',
                         'error_alert_delivery', 'payment_recipient', 'background_job_schedule'],
    }


class Command(BaseCommand):
    help = 'Read-only configuration and account inventory; emits counts and booleans, never credentials.'

    def add_arguments(self, parser):
        parser.add_argument('--strict', action='store_true', help='Exit nonzero if a scoped check fails.')

    def handle(self, *args, **options):
        try:
            report = build_report(User.objects.values('username', 'role', 'is_active').iterator(), settings)
        except Exception:
            raise CommandError('Readiness inspection failed; connection details suppressed.') from None
        self.stdout.write(json.dumps(report, sort_keys=True))
        if options['strict'] and not report['checks_passed']:
            raise CommandError('Production readiness checks failed; inspect the JSON report.')
