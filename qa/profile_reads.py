"""Read-only in-process query profile on the isolated capacity fixture."""
import json
import os
from pathlib import Path
import sys
import time

if not os.environ.get('DB_NAME','').startswith('verify_'):
    raise SystemExit('Use the isolated verify database')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from shop.models import User

client=Client()
client.force_login(User.objects.get(username='+77019999999'))
for path in ['/notifications','/orders?limit=20','/catalog?delivery_date='+str(timezone.localdate()),'/balance']:
    started=time.monotonic()
    with CaptureQueriesContext(connection) as queries:
        response=client.get('/api/v1'+path)
    print(json.dumps({'path':path,'status':response.status_code,'milliseconds':round((time.monotonic()-started)*1000,2),'queries':len(queries),'query_ms':round(sum(float(q['time']) for q in queries)*1000,2),'slowest':sorted(queries,key=lambda q:float(q['time']),reverse=True)[:3]},ensure_ascii=False))
