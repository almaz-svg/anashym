import io
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


class ProductionReadinessTests(SimpleTestCase):
    def config(self, **changes):
        values = dict(DEBUG=False, SECRET_KEY='s' * 64, ALLOWED_HOSTS=['app.example.com'],
                      SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
                      DATABASES={'default': {'ENGINE': 'django.db.backends.postgresql',
                          'OPTIONS': {'sslmode': 'require', 'options': '-c search_path=bakery'}}},
                      STORAGES={'default': {'BACKEND': 'shop.cloud_storage.SupabasePrivateStorage'}},
                      SUPABASE_URL='https://example.supabase.co', SUPABASE_STORAGE_KEY='private-key',
                      SUPABASE_MEDIA_BUCKET='bakery-private-media')
        values.update(changes)
        return SimpleNamespace(**values)

    def report(self, rows, **changes):
        from shop.management.commands.production_readiness import build_report
        return build_report(rows, self.config(**changes))

    def test_disabled_accounts_cannot_satisfy_required_roles(self):
        result = self.report([{'username': 'person', 'role': 'admin', 'is_active': False}])
        self.assertEqual(result['active_roles'], {'admin': 0, 'cashier': 0, 'courier': 0})
        self.assertFalse(result['checks']['required_roles_active'])

    def test_active_demo_is_detected_without_exposing_identity_or_secrets(self):
        result = self.report([{'username': '+77010000002', 'role': 'admin', 'is_active': True}])
        self.assertEqual(result['active_known_demo_accounts'], 1)
        self.assertFalse(result['checks']['known_demo_accounts_disabled'])
        output = json.dumps(result)
        for private in ['+77010000002', 'private-key', 's' * 64, 'example.supabase.co']:
            self.assertNotIn(private, output)

    def test_secure_config_and_real_active_roles_pass_scoped_checks(self):
        result = self.report([{'username': role, 'role': role, 'is_active': True}
                              for role in ['admin', 'cashier', 'courier']])
        self.assertTrue(result['checks_passed'])

    def test_local_defaults_fail_cloud_config_checks(self):
        result = self.report([], DEBUG=True, SECRET_KEY='local-demo-only-change-before-deployment',
                             ALLOWED_HOSTS=['*'], STORAGES={})
        for check in ['debug_disabled', 'strong_secret_configured', 'hosts_restricted', 'private_storage_configured']:
            self.assertFalse(result['checks'][check])

    def test_command_prints_report_then_fails_strict_without_database_write(self):
        # The database is mocked because this audit must not connect to production or start a local DB.
        with patch('shop.management.commands.production_readiness.User.objects.values',
                   return_value=SimpleNamespace(iterator=lambda: iter([]))):
            output = io.StringIO()
            with self.assertRaises(CommandError):
                call_command('production_readiness', strict=True, stdout=output)
            self.assertFalse(json.loads(output.getvalue())['checks_passed'])

    def test_database_failure_does_not_expose_connection_details(self):
        with patch('shop.management.commands.production_readiness.User.objects.values',
                   side_effect=RuntimeError('postgres://private:password@private-host/db')):
            with self.assertRaises(CommandError) as error:
                call_command('production_readiness', stdout=io.StringIO())
            self.assertNotIn('password', str(error.exception))
            self.assertNotIn('private-host', str(error.exception))
