import json
from datetime import datetime,timedelta,timezone
from mvp_http import Session,OUT
from PIL import Image
f=json.loads((OUT/'mvp-edge-fixture.json').read_text());s=Session('http://127.0.0.1:8000');s.login(f['phone'],f['password']);a=Session('http://127.0.0.1:8000');a.login('+77010000002','DemoAdmin2026!')
day=datetime.now(timezone(timedelta(hours=5))).date()
f['baseline_balance']=s.call('balance')['balance_amount']
for key,mode,rows in [('partial_order','deferred',[(f['product_id'],3,1600),(f['product2_id'],2,2000)]),('cash_order','cash',[(f['product_id'],2,1600)])]:
 o=s.call('orders',dict(kind='regular',delivery_point_id=f['point_id'],requested_delivery_at=str(day)+'T18:00:00+05:00',payment_mode=mode,items=[dict(product_id=p,quantity=q,expected_unit_price=str(price)) for p,q,price in rows]),201)
 for status in ['accepted','preparing','ready','out_for_delivery']:
  o=a.call('orders/'+o['id']+'/transition',dict(status=status,courier_id=f['courier_id'],version=o['version']))
 f[key]=o['id']
Image.new('RGB',(120,80),(20,140,80)).save(OUT/'mvp-proof.png')
(OUT/'mvp-ui-fixture.json').write_text(json.dumps(f),encoding='utf-8')
print('UI fixture prepared',f['partial_order'],f['cash_order'])
