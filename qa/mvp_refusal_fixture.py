import json
from datetime import datetime,timezone,timedelta
from mvp_http import Session,OUT
f=json.loads((OUT/'mvp-final-ui-fixture.json').read_text());a=Session('http://127.0.0.1:8000');a.login('+77010000002','DemoAdmin2026!');a.call('products/'+f['product_id']+'/update',dict(active=True,reason='QA refusal fixture'))
day=datetime.now(timezone(timedelta(hours=5))).date();o=a.call('orders',dict(client_id=f['client_id'],kind='regular',delivery_point_id=f['point_id'],requested_delivery_at=str(day)+'T18:00:00+05:00',payment_mode='deferred',items=[dict(product_id=f['product_id'],quantity=1,expected_unit_price='1600')]),201)
f['refusal_original_date']=o['requested_delivery_at'];o=a.call('orders/'+o['id']+'/reschedule',dict(requested_delivery_at=str(day+timedelta(days=1))+'T18:00:00+05:00',version=o['version'],reason='QA refusal real UI'));f['refusal_order']=o['id'];(OUT/'mvp-final-ui-fixture.json').write_text(json.dumps(f),encoding='utf-8')
