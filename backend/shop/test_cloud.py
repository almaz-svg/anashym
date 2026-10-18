import io
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from django.test import SimpleTestCase, override_settings
from django.core.exceptions import ImproperlyConfigured


class CloudConfigurationTests(SimpleTestCase):
    def test_pooler_disables_prepared_statements_and_requires_tls(self):
        from config.cloud import database_from_url
        result = database_from_url('postgresql://postgres.ref:p%40ss@aws-0.pooler.supabase.com:6543/postgres')
        self.assertEqual(result['PASSWORD'], 'p@ss')
        self.assertEqual(result['OPTIONS']['sslmode'], 'require')
        self.assertIsNone(result['OPTIONS']['prepare_threshold'])
        self.assertEqual(result['CONN_MAX_AGE'], 0)
        self.assertTrue(result['DISABLE_SERVER_SIDE_CURSORS'])
        self.assertIn('bakery', result['OPTIONS']['options'])

    def test_missing_database_is_rejected(self):
        from config.cloud import database_from_url
        with self.assertRaises(ImproperlyConfigured):
            database_from_url('')


@override_settings(SUPABASE_URL='https://example.supabase.co', SUPABASE_STORAGE_KEY='server-secret', SUPABASE_MEDIA_BUCKET='private-media')
class PrivateStorageTests(SimpleTestCase):
    def test_read_uses_server_authentication(self):
        from shop.cloud_storage import SupabasePrivateStorage
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'photo'
        with patch('shop.cloud_storage.urlopen', return_value=response) as request:
            content = SupabasePrivateStorage().open('private/photo.jpg').read()
        self.assertEqual(content, b'photo')
        sent = request.call_args.args[0]
        self.assertEqual(sent.get_header('Authorization'), 'Bearer server-secret')
        self.assertIn('/object/authenticated/private-media/private/photo.jpg', sent.full_url)

    def test_exists_does_not_hide_provider_outage(self):
        from shop.cloud_storage import SupabasePrivateStorage
        with patch('shop.cloud_storage.urlopen', side_effect=HTTPError('https://example', 503, 'down', {}, io.BytesIO(b''))):
            with self.assertRaises(OSError):
                SupabasePrivateStorage().exists('private/photo.jpg')

    def test_missing_object_is_false(self):
        from shop.cloud_storage import SupabasePrivateStorage
        with patch('shop.cloud_storage.urlopen', side_effect=HTTPError('https://example', 404, 'missing', {}, io.BytesIO(b''))):
            self.assertFalse(SupabasePrivateStorage().exists('private/photo.jpg'))

    def test_private_storage_does_not_issue_public_urls(self):
        from shop.cloud_storage import SupabasePrivateStorage
        with self.assertRaises(NotImplementedError):
            SupabasePrivateStorage().url('private/photo.jpg')


@override_settings(CLOUD_JOB_SECRET='scheduler-test-secret-at-least-32-characters')
class CloudJobTests(SimpleTestCase):
    secret = 'scheduler-test-secret-at-least-32-characters'

    def test_get_cannot_run_jobs(self):
        response = self.client.get('/api/internal/jobs')
        self.assertEqual(response.status_code, 405)

    def test_missing_or_wrong_bearer_is_forbidden(self):
        for header in ('', 'Bearer wrong', self.secret, 'Basic ' + self.secret):
            response = self.client.post('/api/internal/jobs', HTTP_AUTHORIZATION=header)
            self.assertEqual(response.status_code, 403)

    def test_unconfigured_or_short_secret_fails_closed(self):
        for secret in ('', 'short', ' ' * 40):
            with self.settings(CLOUD_JOB_SECRET=secret):
                response = self.client.post('/api/internal/jobs', HTTP_AUTHORIZATION='Bearer ' + secret)
                self.assertEqual(response.status_code, 503)

    def test_authorized_post_runs_without_csrf_cookie(self):
        from django.test import Client
        with patch('shop.cloud_jobs.call_command') as execute:
            response = Client(enforce_csrf_checks=True).post('/api/internal/jobs',
                HTTP_AUTHORIZATION='Bearer ' + self.secret)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})
        self.assertEqual(execute.call_args.args, ('run_background_jobs',))
        self.assertEqual(response.headers['Cache-Control'], 'no-store')

    def test_failure_does_not_expose_exception_or_command_output(self):
        def fail(*args, **kwargs):
            kwargs['stderr'].write('private database password')
            raise RuntimeError('secret provider URL')
        with patch('shop.cloud_jobs.call_command', side_effect=fail):
            response = self.client.post('/api/internal/jobs', HTTP_AUTHORIZATION='Bearer ' + self.secret)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})

    def test_ordinary_api_post_still_requires_csrf(self):
        from django.test import Client
        response = Client(enforce_csrf_checks=True).post('/api/v1/auth/login', {})
        self.assertEqual(response.status_code, 403)
