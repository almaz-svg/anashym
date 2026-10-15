"""Restore backup into a newly created isolated database; verify ledger and file hashes.

The generated verification database is retained for inspection. This script never
restores into the application's existing database or drops any database.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
import zipfile

from backup import ROOT, connection_args, pg_bin, pg_env


def verify(backup_path):
    started = time.monotonic()
    database = 'verify_' + uuid.uuid4().hex[:16]
    destination = ROOT / 'restore-checks' / database
    destination.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(backup_path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        dump = archive.read('database.dump')
        if hashlib.sha256(dump).hexdigest() != manifest['database_sha256']:
            raise ValueError('Database backup checksum mismatch')
        dump_path = destination / 'database.dump'
        dump_path.write_bytes(dump)
        for name,entry in manifest['media'].items():
            target = (destination / 'media' / name).resolve()
            if not target.is_relative_to(destination.resolve() / 'media'):
                raise ValueError('Unsafe archive path')
            content = archive.read('media/' + name)
            if hashlib.sha256(content).hexdigest() != entry['sha256']:
                raise ValueError('Media checksum mismatch')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(content)
    base = connection_args()
    subprocess.run([pg_bin('createdb'),*base[:6],database],env=pg_env(),check=True,capture_output=True)
    subprocess.run([pg_bin('pg_restore'),*connection_args(database),'--no-owner','--exit-on-error',str(dump_path)],env=pg_env(),check=True,capture_output=True)
    sql = "SELECT json_build_object('orders',(SELECT count(*) FROM shop_order),'ledger_count',(SELECT count(*) FROM shop_ledgerentry),'ledger_total',(SELECT coalesce(sum(amount),0)::text FROM shop_ledgerentry),'photos',(SELECT coalesce(json_agg(file),'[]'::json) FROM shop_photo))"
    result = subprocess.run([pg_bin('psql'),*connection_args(database),'-tA','-c',sql],env=pg_env(),check=True,capture_output=True,text=True,encoding='utf-8')
    restored = json.loads(result.stdout.strip())
    reconciliation_sql="SELECT count(*) FROM (SELECT c.id FROM shop_client c LEFT JOIN shop_ledgerentry l ON l.client_id=c.id GROUP BY c.id HAVING c.balance<>coalesce(sum(l.amount),0)) mismatches"
    reconciliation=subprocess.run([pg_bin('psql'),*connection_args(database),'-tA','-c',reconciliation_sql],env=pg_env(),check=True,capture_output=True,text=True,encoding='utf-8')
    restored['balance_mismatches']=int(reconciliation.stdout.strip())
    if restored['balance_mismatches']:
        raise ValueError('Restored cached balances do not reconcile with the ledger')
    missing = [name for name in restored['photos'] if name not in manifest['media']]
    if missing:
        raise ValueError('Restored DB references missing media')
    restored.update({'database':database,'files_verified':len(manifest['media']),
                     'seconds':round(time.monotonic()-started,3),'passed':True,'directory':str(destination)})
    (destination/'result.json').write_text(json.dumps(restored,ensure_ascii=False,indent=2),encoding='utf-8')
    return restored


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('backup')
    args = parser.parse_args()
    print(json.dumps({key:value for key,value in verify(args.backup).items() if key!='photos'},ensure_ascii=False))
