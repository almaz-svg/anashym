"""Independent real-HTTP acceptance. Never imports application services/models.
Run backend/.venv/Scripts/python qa/mvp_http.py --base http://127.0.0.1:8000
Creates only uniquely named QA records; does not delete financial history.
"""
import argparse, base64, csv, io, json, time, uuid
import urllib.request, urllib.error, http.cookiejar
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

OUT = Path(__file__).parent
RESULTS = []

def check(name, condition, detail=None):
    RESULTS.append(dict(name=name, pass_=bool(condition), detail=detail))
    print(('PASS ' if condition else 'FAIL ') + name, detail or '')
    if not condition:
        raise AssertionError(name)

class Session:
    def __init__(self, base):
        self.base = base.rstrip('/') + '/api/v1/'
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
    def call(self, route, data=None, expected=200, key=None, raw=None, content_type=None):
        headers = {'Accept':'application/json'}
        if data is not None or raw is not None:
            headers.update({'Content-Type':content_type or 'application/json',
                'X-CSRFToken':next((c.value for c in self.jar if c.name=='csrftoken'), ''),
                'Idempotency-Key':key or str(uuid.uuid4()), 'Origin':self.base.split('/api/')[0]})
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.base+route, data=body, headers=headers)
        try: response = self.opener.open(req)
        except urllib.error.HTTPError as e: response = e
        payload = response.read()
        self.last_headers=dict(response.headers)
        self.last_status=response.status
        parsed = json.loads(payload) if 'json' in response.headers.get('Content-Type','') and payload else payload
        if expected is not None and response.status != expected:
            raise AssertionError(f'{route}: expected {expected}, got {response.status}: {str(parsed)[:1200]}')
        return parsed
    def login(self, phone, password):
        self.call('auth/csrf', expected=204)
        return self.call('auth/login',dict(phone=phone,password=password))
    def upload(self, order, purpose='delivery'):
        # Actual decodable 1x1 PNG, sent as multipart rather than fake metadata.
        from PIL import Image
        buffer=io.BytesIO();Image.new('RGB',(24,24),(40,120,70)).save(buffer,format='PNG');png=buffer.getvalue()
        boundary='QA'+uuid.uuid4().hex
        parts=[]
        for name,value in [('order_id',order),('purpose',purpose)]:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="qa.png"\r\nContent-Type: image/png\r\n\r\n'.encode()+png+b'\r\n')
        parts.append(f'--{boundary}--\r\n'.encode())
        result=self.call('files',expected=201,raw=b''.join(parts),content_type='multipart/form-data; boundary='+boundary)
        return result['id'] if 'id' in result else result['items'][0]['id']

def main(base):
    actors={role:Session(base) for role in ['customer','admin','courier','cashier','accountant']}
    fixture=json.loads((OUT/'mvp-fixture.json').read_text())
    for index,(role,session) in enumerate(actors.items(),1):
        me=session.login(fixture['phone'] if index==1 else '+7701000000'+str(index), fixture['password'] if index==1 else 'DemoAdmin2026!' if index==2 else 'DemoStaff2026!')
        check('login '+role,me['role']==role)
    customer,admin,courier,cashier,accountant=(actors[x] for x in actors)
    # The baseline is read once: assertions measure deltas, never assume empty demo state.
    client=customer.call('auth/me')['client_id']
    balance=lambda:Decimal(customer.call('balance')['balance_amount'])
    baseline=balance()
    point=customer.call('delivery-points')['items'][0]['id']
    product=admin.call('products',dict(name='QA HTTP '+uuid.uuid4().hex[:10],description='Isolated acceptance fixture',price_amount='1500.00',preparation_minutes=1),201)
    pid=product['id']
    fixture_log=OUT/'mvp-created-products.json'
    created=json.loads(fixture_log.read_text()) if fixture_log.exists() else []
    created.append(pid);fixture_log.write_text(json.dumps(created),encoding='utf-8')
    now=datetime.now(timezone.utc)
    admin.call('batches',dict(product_id=pid,manufactured_at=(now-timedelta(hours=1)).isoformat(),expires_at=(now+timedelta(days=3)).isoformat(),quantity=100),201)
    day=datetime.now(timezone(timedelta(hours=5))).date()
    payload=dict(kind='regular',delivery_point_id=point,requested_delivery_at=str(day)+'T18:00:00+05:00',payment_mode='deferred',items=[dict(product_id=pid,quantity=10,expected_unit_price='1500.00')])
    key=str(uuid.uuid4())
    order=customer.call('orders',payload,201,key)
    check('order idempotent replay',customer.call('orders',payload,201,key)['id']==order['id'])
    changed={**payload,'items':[dict(product_id=pid,quantity=9,expected_unit_price='1500.00')]}
    customer.call('orders',changed,409,key)
    oid=order['id']
    courier_id=courier.call('auth/me')['user_id']
    def transition(status):
        current=admin.call('orders/'+oid)
        return admin.call('orders/'+oid+'/transition',dict(status=status,courier_id=courier_id,version=current['version']))
    for state in ['accepted','preparing','ready','out_for_delivery']: transition(state)
    current=courier.call('orders/'+oid)
    delivered=dict(items=[dict(product_id=pid,quantity=10)],photo_ids=[],version=current['version'])
    courier.call('orders/'+oid+'/delivery',delivered,422)
    check('missing photo delivery rolls back debt',balance()==baseline)
    photo=courier.upload(oid)
    delivered['photo_ids']=[photo]
    courier.call('orders/'+oid+'/delivery',delivered)
    check('delivery charge 15000',balance()-baseline==Decimal('15000'))
    admin.call('orders/'+oid+'/assign-collection',dict(courier_id=courier_id,reason='QA assigned debt collection'))
    cash_photo=courier.upload(oid,'cash')
    cash=courier.call('payments',dict(client_id=client,order_id=oid,method='cash',amount='10000.00',photo_ids=[cash_photo]),201)
    check('cash immediately reduces debt to 5000',balance()-baseline==Decimal('5000'))
    handover=courier.call('handovers',dict(amount='10000.00'),201)
    cashier.call('handovers/'+handover['id']+'/confirm',dict(amount='10000.00'))
    check('handover does not double post payment',balance()-baseline==Decimal('5000'))
    return_photo=customer.upload(oid,'return')
    ret=customer.call('returns',dict(order_id=oid,kind='return',items=[dict(product_id=pid,quantity=1)],reason='QA return',photo_ids=[return_photo]),201)
    admin.call('returns/'+ret['id']+'/decide',dict(decision='approve',reason='QA pending physical receipt',disposition='quarantine'))
    check('approval alone creates no return credit',balance()-baseline==Decimal('5000'))
    receipt_photo=admin.upload(oid,'return')
    admin.call('returns/'+ret['id']+'/receive',dict(reason='QA physically received',photo_ids=[receipt_photo]))
    check('received return reduces debt to 3500',balance()-baseline==Decimal('3500'))
    pending=customer.call('payments',dict(order_id=oid,method='kaspi',amount='3500.00',reference='QA-'+uuid.uuid4().hex),201)
    check('Kaspi remains pending',pending.get('state',pending.get('status')) in ['pending_review','pending'] and balance()-baseline==Decimal('3500'))
    cashier.call('payments/'+pending['id']+'/confirm',{})
    check('confirmed Kaspi settles debt',balance()==baseline)
    for role,session in actors.items():
        for route in ['orders','payments','notifications']:
            data=session.call(route)
            check(role+' '+route+' envelope',isinstance(data.get('items'),list))
    customer.call('audit',expected=403)
    report=accountant.call(f'reports?from={day}&to={day}&group=weekly')
    check('report contains independent totals',isinstance(report.get('totals'),dict),report.get('totals'))
    raw=accountant.call(f'reports?from={day}&to={day}&format=csv')
    rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    check('CSV has source traceability',bool(rows) and all(k in rows[0] for k in ['event_at','business_date','kind','amount']))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8000');args=parser.parse_args()
    try: main(args.base)
    except Exception as error:
        RESULTS.append(dict(name='runner failure',pass_=False,detail=str(error)));raise
    finally: (OUT/'mvp-http-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
