import api_checks as qa
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from shop.models import Quota, Order, Product
import uuid, json
from pathlib import Path
try:
    s,c,p,b,body,phone=qa.fixture()
    tomorrow=timezone.localdate()+timedelta(days=1)
    quota=Quota.objects.create(product=p,date=tomorrow,cutoff=timezone.now()+timedelta(hours=1),quantity=15)
    body['kind']='preorder'
    body['requested_delivery_at']=tomorrow.isoformat()+'T12:00:00+05:00'
    status,order=s.call('POST','/orders',body,uuid.uuid4())
    qa.expect('preorder accepted',status==201,(status,order))
    quota.refresh_from_db();b.refresh_from_db()
    qa.expect('preorder reserves quota only',quota.reserved==10 and b.reserved==0)
    Order.objects.filter(id=order['id']).update(reservation_expires_at=timezone.now()-timedelta(seconds=1))
    call_command('expire_reservations')
    quota.refresh_from_db();c.refresh_from_db()
    qa.expect('expiry releases quota and credit',quota.reserved==0 and c.reserved_credit==0 and Order.objects.get(id=order['id']).status=='cancelled')
    call_command('expire_reservations')
    quota.refresh_from_db();c.refresh_from_db()
    qa.expect('expiry second run no double release',quota.reserved==0 and c.reserved_credit==0 and Order.objects.get(id=order['id']).version==2)
    quota.cutoff=timezone.now()-timedelta(seconds=1);quota.save()
    rejection=s.call('POST','/orders',body,uuid.uuid4())
    qa.expect('quota cutoff enforced',rejection[0]==409 and rejection[1].get('code')=='STOCK_UNAVAILABLE',rejection)
    Product.objects.filter(name__startswith='QA ').update(active=False)
finally:
    Path(__file__).with_name('expiry-quota-results.json').write_text(json.dumps(qa.results,ensure_ascii=False,indent=2),encoding='utf8')
if any(not x['passed'] for x in qa.results): raise SystemExit(1)
