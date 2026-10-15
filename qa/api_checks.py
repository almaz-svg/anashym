"""Independent black-box HTTP checks, with isolated PostgreSQL fixture setup.
Run using backend/.venv Python, with the same DB_* environment as the server.
Never points at production: requires QA_ALLOW_FIXTURES=1 and PostgreSQL.
"""
import os, sys, json, uuid, urllib.request, urllib.error, http.cookiejar
from pathlib import Path
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import django
django.setup()
from django.db import connection
from django.utils import timezone
from shop.models import Client, User, DeliveryPoint, Product, Batch, Order
assert os.environ.get('QA_ALLOW_FIXTURES') == '1', 'Explicit test-fixture permission required'
assert connection.vendor == 'postgresql', 'Concurrency evidence requires PostgreSQL'
BASE = os.environ.get('QA_API_URL', 'http://127.0.0.1:8000/api/v1')
PASSWORD = 'QaLocalOnly-2026!'
results = []

class Session:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.call('GET', '/auth/csrf')
    def call(self, method, path, data=None, key=None, csrf=True):
        headers = {'Content-Type':'application/json', 'Referer':BASE + '/'}
        if csrf:
            for c in self.cookies:
                if c.name == 'csrftoken': headers['X-CSRFToken'] = c.value
        if key: headers['Idempotency-Key'] = str(key)
        req = urllib.request.Request(BASE + path, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method)
        try: response = self.opener.open(req, timeout=20)
        except urllib.error.HTTPError as e: response = e
        raw = response.read()
        try: body = json.loads(raw) if raw else None
        except ValueError: body = {'non_json':raw.decode(errors='replace')[:300]}
        return response.status, body

def expect(name, condition, detail=None):
    results.append({'check':name, 'passed':bool(condition), 'detail':detail})
    print(('PASS ' if condition else 'FAIL ') + name, detail or '')

def fixture(stock=20, debt='0.00', limit='50000.00'):
    tag = uuid.uuid4().hex[:8]
    client = Client.objects.create(name='QA '+tag, category='coffee_shop', description='Independent QA', expected_order_quantity=10, expected_order_frequency='daily', approval_status='active', deferred_approved=True, credit_limit=limit, balance=debt)
    phone = '+77' + str(uuid.uuid4().int % 10**9).zfill(9)
    User.objects.create_user(username=phone, password=PASSWORD, client=client, role='customer')
    point = DeliveryPoint.objects.create(client=client,address='QA local only',recipient='QA',phone=phone,window_start='00:00',window_end='23:59:59')
    product = Product.objects.create(name='QA '+tag,price='1500.00',preparation_minutes=0)
    now=timezone.now()
    batch=Batch.objects.create(product=product,manufactured_at=now-timedelta(hours=1),expires_at=now+timedelta(days=2),quantity=stock)
    session=Session()
    status, body=session.call('POST','/auth/login',{'phone':phone,'password':PASSWORD})
    assert status == 200, (status,body)
    payload={'kind':'regular','delivery_point_id':str(point.id),'requested_delivery_at':(now+timedelta(minutes=2)).isoformat(),'payment_mode':'deferred','items':[{'product_id':str(product.id),'quantity':10,'expected_unit_price':'1500.00'}]}
    return session, client, product, batch, payload, phone

def race(sessions, payloads, keys):
    gate=Barrier(2)
    def send(i):
        gate.wait()
        return sessions[i].call('POST','/orders',payloads[i],keys[i])
    with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(send,range(2)))

def run():
    anonymous=Session()
    expect('unauthenticated balance',anonymous.call('GET','/balance')[0]==401)
    s,c,p,b,body,phone=fixture()
    expect('login session/me',s.call('GET','/auth/me')[0]==200)
    expect('CSRF required',s.call('POST','/orders',body,uuid.uuid4(),csrf=False)[0]==403)
    key=uuid.uuid4(); status,order=s.call('POST','/orders',body,key)
    expect('create order 10 x 1500',status==201 and order.get('total_amount')=='15000.00',(status,order))
    repeat=s.call('POST','/orders',body,key)
    expect('idempotent replay same response',repeat==(status,order),repeat)
    altered={**body,'items':[{**body['items'][0],'quantity':9}]}
    conflict=s.call('POST','/orders',altered,key)
    expect('idempotency changed body 409',conflict[0]==409 and conflict[1].get('code')=='IDEMPOTENCY_CONFLICT',conflict)
    balance=s.call('GET','/balance')[1]
    expect('reserve credit without creating debt',balance.get('reserved_credit_amount')=='15000.00' and balance.get('debt_amount')=='0.00' and balance.get('available_credit_amount')=='35000.00',balance)
    b.refresh_from_db(); expect('stock reservation exactly once',b.reserved==10,b.reserved)
    other,*_=fixture()
    expect('foreign order hidden',other.call('GET','/orders/'+str(order.get('id')))[0]==404)
    expect('foreign delivery point rejected',other.call('POST','/orders',body,uuid.uuid4())[0]==404)
    bad={**body,'items':[{**body['items'][0],'expected_unit_price':'1499.00'}]}
    rejection=s.call('POST','/orders',bad,uuid.uuid4())
    expect('price mismatch',rejection[0]==409 and rejection[1].get('code')=='PRICE_CHANGED',rejection)
    b.refresh_from_db(); expect('price mismatch leaves stock unchanged',b.reserved==10)
    unknown=s.call('POST','/orders',{**body,'unexpected':'x'},uuid.uuid4())
    expect('unknown field rejected',unknown[0]==422,unknown)
    reg={'phone':'+77'+str(uuid.uuid4().int%10**9).zfill(9),'password':PASSWORD,'name':'QA pending','description':'QA','expected_order_quantity':1,'expected_order_frequency':'weekly'}
    expect('registration category required',anonymous.call('POST','/auth/register',reg)[0]==422)
    expect('registration other explanation required',anonymous.call('POST','/auth/register',{**reg,'category':'other','category_other':'  '})[0]==422)
    registered=anonymous.call('POST','/auth/register',{**reg,'category':'other','category_other':'QA explanation'})
    expect('valid registration accepted',registered[0]==201,registered)
    pending=Session(); pending.call('POST','/auth/login',{'phone':reg['phone'],'password':PASSWORD})
    expect('pending cannot access catalog',pending.call('GET','/catalog')[0]==403)
    for name,stock,debt,qty,expected_code in [('stock race',10,'0.00',7,'STOCK_UNAVAILABLE'),('credit race',100,'30000.00',10,'CREDIT_LIMIT_EXCEEDED')]:
        s,c,p,b,body,phone=fixture(stock=stock,debt=debt)
        body['items'][0]['quantity']=qty
        second=Session(); second.call('POST','/auth/login',{'phone':phone,'password':PASSWORD})
        responses=race([s,second],[body,body],[uuid.uuid4(),uuid.uuid4()])
        expect(name+' one success one conflict',sorted(x[0] for x in responses)==[201,409] and any(x[1].get('code')==expected_code for x in responses),responses)
        b.refresh_from_db(); c.refresh_from_db()
        expect(name+' DB invariants',b.reserved==qty and c.reserved_credit==1500*qty and Order.objects.filter(client=c).count()==1,{'stock_reserved':b.reserved,'credit_reserved':str(c.reserved_credit)})
    s,c,p,b,body,phone=fixture()
    second=Session(); second.call('POST','/auth/login',{'phone':phone,'password':PASSWORD})
    key=uuid.uuid4(); responses=race([s,second],[body,body],[key,key])
    expect('concurrent same idempotency key',responses[0]==responses[1] and responses[0][0]==201,responses)
    expect('concurrent duplicate creates one order',Order.objects.filter(client=c).count()==1)

if __name__ == '__main__':
    try: run()
    finally:
        Path(__file__).with_name('api-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(not x['passed'] for x in results): sys.exit(1)
