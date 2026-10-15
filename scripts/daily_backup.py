import json
from datetime import datetime
from zoneinfo import ZoneInfo
from backup import ROOT,backup

day=datetime.now(ZoneInfo('Asia/Almaty')).date().isoformat()
destination=ROOT/'backups'/('daily-'+day+'.zip')
if destination.exists():
    print(json.dumps({'backup':str(destination),'status':'already_exists'}))
else:
    print(json.dumps(backup(destination),ensure_ascii=False))
