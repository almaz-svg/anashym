"""Create a PostgreSQL custom dump + private media backup, never logs credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
import zipfile
import uuid

ROOT = Path(__file__).resolve().parents[1]


def pg_bin(name):
    override = os.environ.get('PG_BIN')
    candidates = [Path(override) / (name + '.exe')] if override else []
    candidates += [Path('C:/Program Files/PostgreSQL/18/bin') / (name + '.exe')]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name) or name


def connection_args(database=None):
    return ['-h', os.environ.get('DB_HOST','127.0.0.1'), '-p', os.environ.get('DB_PORT','54329'),
            '-U',os.environ.get('DB_USER','confectionery'), '-d',database or os.environ.get('DB_NAME','confectionery')]


def pg_env():
    env = os.environ.copy()
    env['PGPASSWORD'] = env.get('DB_PASSWORD','')
    return env


def backup(destination, media_root=None):
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True,exist_ok=True)
    media_root = Path(media_root or ROOT / 'backend/media').resolve()
    stamp = datetime.now(timezone.utc).isoformat()
    manifest = {'created_at':stamp, 'format':1, 'database':os.environ.get('DB_NAME','confectionery'), 'media':{}}
    with tempfile.TemporaryDirectory(prefix='bakery-backup-') as work:
        dump = Path(work) / 'database.dump'
        subprocess.run([pg_bin('pg_dump'),*connection_args(),'-Fc','--no-owner','-f',str(dump)],env=pg_env(),check=True,capture_output=True)
        manifest['database_sha256'] = hashlib.sha256(dump.read_bytes()).hexdigest()
        staged = destination.parent / ('.partial-' + uuid.uuid4().hex + '.zip')
        try:
            with zipfile.ZipFile(staged,'x',compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(dump,'database.dump')
                if media_root.exists():
                    for source in sorted(media_root.rglob('*')):
                        if not source.is_file():
                            continue
                        relative = source.relative_to(media_root).as_posix()
                        content = source.read_bytes()
                        manifest['media'][relative] = {'sha256':hashlib.sha256(content).hexdigest(),'size':len(content)}
                        archive.writestr('media/' + relative,content)
                archive.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            # Atomic publication on the local NTFS volume, refusing existing backups.
            os.link(staged,destination)
        finally:
            staged.unlink(missing_ok=True)
    return {'backup':str(destination),'media_count':len(manifest['media']),'created_at':stamp}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',default=str(ROOT / 'backups' / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '.zip')))
    parser.add_argument('--media-root')
    args = parser.parse_args()
    print(json.dumps(backup(args.output,args.media_root),ensure_ascii=False))
