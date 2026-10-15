"""Run through manage.py shell to create isolated acceptance client and point."""
import json, uuid
from pathlib import Path
from django.utils import timezone
from shop.models import Client, User, DeliveryPoint
tag=uuid.uuid4().hex[:10]
phone='+779'+str(uuid.uuid4().int)[0:8]
client=Client.objects.create(name='QA HTTP '+tag, approval_status='active',deferred_approved=True,credit_limit='1000000',period_start=timezone.localdate(),period_days=7)
user=User.objects.create_user(username=phone,password='QaHttp2026!',client=client,role='customer')
point=DeliveryPoint.objects.create(client=client,address='QA isolated address',recipient='QA',phone=phone)
Path('../qa/mvp-fixture.json').write_text(json.dumps(dict(phone=phone,password='QaHttp2026!',client_id=str(client.pk),point_id=str(point.pk))),encoding='utf-8')
print('Created isolated QA fixture',tag)
