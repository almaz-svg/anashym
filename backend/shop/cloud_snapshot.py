"""Application-level snapshots; offline integrity checks are not restore drills."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
import zipfile


def digest(value):
    return hashlib.sha256(value).hexdigest()


def fixture_summary(content):
    rows = json.loads(content)
    if not isinstance(rows, list):
        raise ValueError('Invalid fixture')
    counts, identities, photos, balances = Counter(), set(), {}, {}
    ledger = defaultdict(Decimal)
    for row in rows:
        model, pk, fields = row['model'], str(row['pk']), row['fields']
        if not (model.startswith('shop.') or model == 'auth.group') or (model, pk) in identities:
            raise ValueError('Unexpected model or duplicate record')
        identities.add((model, pk))
        counts[model] += 1
        if model == 'shop.client':
            balances[pk] = Decimal(fields['balance'])
        if model == 'shop.ledgerentry':
            ledger[str(fields['client'])] += Decimal(fields['amount'])
        if model == 'shop.photo':
            name = fields['file']
            path = PurePosixPath(name)
            if not name or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name or str(path) != name:
                raise ValueError('Unsafe media key')
            info = {'sha256': fields['content_hash'], 'size': fields['size']}
            if name in photos and photos[name] != info:
                raise ValueError('Conflicting media metadata')
            photos[name] = info
    if set(ledger) - set(balances) or any(not amount.is_finite() or amount != ledger[pk] for pk, amount in balances.items()):
        raise ValueError('Client balances do not reconcile with ledger')
    return {'model_counts': dict(sorted(counts.items())), 'media': photos,
            'ledger_total': str(sum(ledger.values(), Decimal('0.00')))}


def write_snapshot(destination, fixture, open_media, metadata):
    destination = Path(destination).resolve()
    if destination.exists():
        raise FileExistsError('Snapshot already exists')
    summary = fixture_summary(fixture)
    manifest = {'format': 'bakery-application-snapshot-v1',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'fixture_sha256': digest(fixture), **summary, 'metadata': metadata}
    descriptor, temporary = tempfile.mkstemp(prefix='.snapshot-', suffix='.zip', dir=destination.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('fixture.json', fixture)
            for name, expected in summary['media'].items():
                with open_media(name) as source:
                    content = source.read()
                if len(content) != expected['size'] or digest(content) != expected['sha256']:
                    raise ValueError('Photo bytes do not match database metadata')
                archive.writestr('media/' + name, content)
            archive.writestr('manifest.json', json.dumps(manifest, sort_keys=True))
        report = verify_snapshot(temporary)
        # Exclusive publication: never replace another backup, even after a race.
        os.link(temporary, destination)
        return report
    finally:
        Path(temporary).unlink(missing_ok=True)


def verify_snapshot(source):
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive entries')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest['format'] != 'bakery-application-snapshot-v1':
            raise ValueError('Unsupported snapshot format')
        fixture = archive.read('fixture.json')
        if digest(fixture) != manifest['fixture_sha256']:
            raise ValueError('Fixture checksum mismatch')
        summary = fixture_summary(fixture)
        if any(manifest[key] != value for key, value in summary.items()):
            raise ValueError('Manifest does not match fixture')
        if set(names) != {'manifest.json', 'fixture.json'} | {'media/' + name for name in summary['media']}:
            raise ValueError('Missing or unexpected archive entries')
        for name, expected in summary['media'].items():
            content = archive.read('media/' + name)
            if len(content) != expected['size'] or digest(content) != expected['sha256']:
                raise ValueError('Media checksum mismatch')
    return {'integrity_verified': True, 'restore_tested': False,
            'model_counts': summary['model_counts'], 'media_count': len(summary['media']),
            'ledger_total': summary['ledger_total'], 'fixture_sha256': manifest['fixture_sha256']}
