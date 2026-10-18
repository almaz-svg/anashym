import importlib
import os
import tempfile
from pathlib import Path
from wsgiref.util import setup_testing_defaults
from unittest.mock import patch
from django.test import SimpleTestCase


class RailwayConfigurationTests(SimpleTestCase):
    def test_same_database_and_domains_include_healthcheck_without_csrf_trust(self):
        from config import settings as module
        try:
            with patch.dict(os.environ, {
                'RAILWAY_ENVIRONMENT_ID': 'test-environment',
                'RAILWAY_PUBLIC_DOMAIN': 'anashym.example.up.railway.app',
                'DJANGO_SECRET_KEY': 'x' * 64,
                'DATABASE_URL': 'postgresql://existing:password@db.example.test/postgres',
            }, clear=True):
                config = importlib.reload(module)
                self.assertIn('healthcheck.railway.app', config.ALLOWED_HOSTS)
                self.assertIn('anashym.example.up.railway.app', config.ALLOWED_HOSTS)
                self.assertNotIn('https://healthcheck.railway.app', config.CSRF_TRUSTED_ORIGINS)
                self.assertEqual(config.DATABASES['default']['OPTIONS']['options'], '-c search_path=bakery')
                self.assertFalse(config.DEBUG)
                self.assertTrue(config.SESSION_COOKIE_SECURE)
        finally:
            importlib.reload(module)

    def test_frontend_static_and_api_are_served_without_exposing_media(self):
        from config.railway import build_application
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for folder in ('frontend-dist', 'staticfiles', 'media'):
                (root / folder).mkdir()
            (root / 'frontend-dist/index.html').write_text('<html>app</html>')
            (root / 'staticfiles/admin.css').write_text('body{}')
            (root / 'media/private.jpg').write_bytes(b'private')
            app = build_application(root)
            for path, status, expected in [('/', '200', b'<html>app</html>'),
                    ('/static/admin.css', '200', b'body{}'), ('/live', '200', b'"live"'),
                    ('/media/private.jpg', '404', None)]:
                env = {}
                setup_testing_defaults(env)
                env.update(PATH_INFO=path, HTTP_HOST='testserver')
                captured = []
                response = app(env, lambda response_status, headers: captured.append(response_status))
                try:
                    body = b''.join(response)
                finally:
                    if hasattr(response, 'close'):
                        response.close()
                self.assertTrue(captured[0].startswith(status), captured)
                if expected:
                    self.assertIn(expected, body)
