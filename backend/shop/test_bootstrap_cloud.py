"""Cloud bootstrap orchestration, with no database or network side effects."""
import io
import os
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from shop.management.commands.bootstrap_cloud import Command


@override_settings(SUPABASE_STORAGE_KEY='test-only', SUPABASE_MEDIA_BUCKET='private-media')
class CloudBootstrapSeedTests(SimpleTestCase):
    def bootstrap(self, environment):
        output = io.StringIO()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"public": false}'
        with patch.dict(os.environ, environment, clear=True), \
                patch('shop.management.commands.bootstrap_cloud.connection') as connection, \
                patch('shop.management.commands.bootstrap_cloud.transaction.atomic', return_value=nullcontext()), \
                patch('shop.management.commands.bootstrap_cloud.call_command') as commands, \
                patch('shop.management.commands.bootstrap_cloud.SupabasePrivateStorage') as storage:
            connection.settings_dict = {'OPTIONS': {'options': '-c search_path=bakery'}}
            storage.return_value._request.return_value = response
            Command(stdout=output).handle()
            storage.return_value._request.assert_called_once_with('bucket/private-media')
            return commands.call_args_list, output.getvalue()

    def test_default_migrates_and_checks_storage_without_seeding(self):
        calls, output = self.bootstrap({})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].args, ('migrate',))
        self.assertEqual(calls[0].kwargs, {'interactive': False, 'verbosity': 0})
        self.assertIn('private storage are ready', output)
        self.assertNotIn('demo accounts', output)

    def test_only_exact_explicit_opt_in_seeds(self):
        for value in ['', '0', 'true', 'yes', ' 1 ']:
            with self.subTest(value=value):
                calls, _ = self.bootstrap({'CLOUD_SEED_DEMO': value})
                self.assertEqual([call.args[0] for call in calls], ['migrate'])
        calls, output = self.bootstrap({'CLOUD_SEED_DEMO': '1'})
        self.assertEqual([call.args[0] for call in calls], ['migrate', 'seed_demo'])
        self.assertIn('Demo seed requested', output)
