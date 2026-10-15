import json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
if not os.environ.get('DB_NAME','').startswith('verify_'): raise SystemExit('Isolated verification DB required')
import django
django.setup()
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import Client
from django.utils import timezone
from shop.models import User

client=Client()
user=User.objects.filter(first_name='Synthetic load').first()
client.force_login(user)
for path in ['/notifications','/orders?limit=20','/catalog?delivery_date='+timezone.localdate().isoformat(),'/balance']:
    started=time.perf_counter()
    with CaptureQueriesContext(connection) as capture:
        response=client.get('/api/v1'+path)
    print(json.dumps({'path':path,'status':response.status_code,'elapsed_ms':round((time.perf_counter()-started)*1000,2),'queries':len(capture),'sql_ms':sum(float(q['time'])*1000 for q in capture),'slow_queries':[{'time':q['time'],'sql':q['sql'][:250]} for q in capture if float(q['time'])>.005]},ensure_ascii=False))
