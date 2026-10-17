import io
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from django.test import SimpleTestCase, override_settings
from .cloud_storage import SupabasePrivateStorage


@override_settings(SUPABASE_URL='https://example.supabase.co', SUPABASE_STORAGE_KEY='test-secret', SUPABASE_MEDIA_BUCKET='private-media')
class CloudStorageCleanupTests(SimpleTestCase):
    def test_failed_upload_cleanup_deletes_only_its_object(self):
        with patch('shop.cloud_storage.urlopen', return_value=MagicMock()) as request:
            SupabasePrivateStorage().delete('private/photo.jpg')
        sent = request.call_args.args[0]
        self.assertEqual(sent.method, 'DELETE')
        self.assertEqual(sent.full_url, 'https://example.supabase.co/storage/v1/object/private-media')
        self.assertEqual(json.loads(sent.data), {'prefixes': ['private/photo.jpg']})

    def test_legacy_missing_object_is_false(self):
        error = HTTPError('https://example', 400, 'Bad Request', {}, io.BytesIO(b'{"statusCode":"404","error":"not_found","message":"Object not found"}'))
        with patch('shop.cloud_storage.urlopen', side_effect=error):
            self.assertFalse(SupabasePrivateStorage().exists('private/photo.jpg'))

    def test_invalid_storage_requests_are_not_reported_as_missing_objects(self):
        error = HTTPError('https://example', 400, 'Bad Request', {}, io.BytesIO(b'{"statusCode":"403","message":"Access denied"}'))
        with patch('shop.cloud_storage.urlopen', side_effect=error):
            with self.assertRaises(HTTPError):
                SupabasePrivateStorage().exists('private/photo.jpg')
