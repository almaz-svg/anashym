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


class CloudJobTests(SimpleTestCase):
    def test_jobs_are_not_exposed_as_a_public_http_trigger(self):
        # Railway cron runs the finite management command, not the previously
        # proposed bearer-token HTTP endpoint. Its behavior is covered separately
        # by test_background_jobs against a real test database.
        for method in ('get', 'post'):
            response = getattr(self.client, method)('/api/internal/jobs',
                HTTP_AUTHORIZATION='Bearer job-secret')
            self.assertEqual(response.status_code, 404)
