import hashlib
import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase
from django.core.management import call_command
from django.core.management.base import CommandError


class CloudSnapshotTests(SimpleTestCase):
    def fixture(self):
        return [
            {'model': 'shop.client', 'pk': 'c', 'fields': {'balance': '12.50'}},
            {'model': 'shop.ledgerentry', 'pk': 'l', 'fields': {'client': 'c', 'amount': '12.50'}},
            {'model': 'shop.user', 'pk': 'u', 'fields': {'username': 'person', 'password': 'private-password-hash'}},
            {'model': 'shop.photo', 'pk': 'p', 'fields': {'file': 'private/proof.jpg', 'size': 5,
                'content_hash': hashlib.sha256(b'proof').hexdigest()}},
            {'model': 'shop.weeklyreport', 'pk': 1, 'fields': {'payload': {'total': '12.50', 'rows': [1, 2]}}},
        ]

    def create(self, path, fixture=None, content=b'proof'):
        from shop.cloud_snapshot import write_snapshot
        return write_snapshot(path, json.dumps(fixture if fixture is not None else self.fixture()).encode(),
                              lambda name: io.BytesIO(content), {'migrations': ['shop.0001_initial']})

    def test_round_trip_preserves_password_hash_and_verifies_related_media(self):
        from shop.cloud_snapshot import verify_snapshot
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            self.create(path)
            report = verify_snapshot(path)
            self.assertEqual(report['media_count'], 1)
            self.assertEqual(report['ledger_total'], '12.50')
            self.assertFalse(report['restore_tested'])
            with zipfile.ZipFile(path) as archive:
                self.assertIn(b'private-password-hash', archive.read('fixture.json'))
                rows = json.loads(archive.read('fixture.json'))
                self.assertEqual(rows[-1]['fields']['payload'], {'total': '12.50', 'rows': [1, 2]})
            self.assertNotIn('private-password-hash', json.dumps(report))

    def test_missing_or_wrong_media_fails_without_publishing_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            with self.assertRaises(ValueError):
                self.create(path, content=b'wrong')
            self.assertFalse(path.exists())

    def test_existing_archive_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            path.write_bytes(b'keep')
            with self.assertRaises(FileExistsError):
                self.create(path)
            self.assertEqual(path.read_bytes(), b'keep')

    def test_inconsistent_ledger_is_rejected(self):
        rows = self.fixture()
        rows[0]['fields']['balance'] = '99.00'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.create(Path(folder) / 'snapshot.zip', fixture=rows)

    def test_path_traversal_is_rejected(self):
        rows = self.fixture()
        rows[3]['fields']['file'] = '../escape.jpg'
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                self.create(Path(folder) / 'snapshot.zip', fixture=rows)

    def test_fixture_tampering_is_detected(self):
        from shop.cloud_snapshot import verify_snapshot
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            self.create(path)
            with zipfile.ZipFile(path) as source:
                entries = {name: source.read(name) for name in source.namelist()}
            entries['fixture.json'] = b'[]'
            with zipfile.ZipFile(path, 'w') as target:
                for name, value in entries.items():
                    target.writestr(name, value)
            with self.assertRaises(ValueError):
                verify_snapshot(path)

    def test_export_requires_explicit_paused_writers_before_database_access(self):
        with self.assertRaisesMessage(CommandError, 'Pause application writes'):
            call_command('export_cloud_snapshot', output='unused.zip', stdout=io.StringIO())

    def test_offline_verify_command_does_not_connect_to_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            self.create(path)
            output = io.StringIO()
            call_command('verify_cloud_snapshot', str(path), stdout=output)
            self.assertTrue(json.loads(output.getvalue())['integrity_verified'])

    def test_missing_archive_media_is_rejected(self):
        from shop.cloud_snapshot import verify_snapshot
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'snapshot.zip'
            self.create(path)
            with zipfile.ZipFile(path) as archive:
                entries = {name: archive.read(name) for name in ['fixture.json', 'manifest.json']}
            with zipfile.ZipFile(path, 'w') as archive:
                for name, content in entries.items():
                    archive.writestr(name, content)
            with self.assertRaises(ValueError):
                verify_snapshot(path)
