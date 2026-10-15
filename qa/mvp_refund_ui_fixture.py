import json,uuid
from decimal import Decimal
from mvp_http import Session,OUT
f=json.loads((OUT/'mvp-final-ui-fixture.json').read_text());base='http://127.0.0.1:8000'
c=Session(base);c.login(f['phone'],f['password']);a=Session(base);a.login('+77010000002','DemoAdmin2026!')
balance=Decimal(c.call('balance')['balance_amount']);payment=c.call('payments',dict(method='kaspi',amount=str(balance+Decimal(10)),reference='QA-FINAL-ADVANCE-'+uuid.uuid4().hex),201);a.call('payments/'+payment['id']+'/confirm',dict(reason='QA final isolated advance'))
assert Decimal(c.call('balance')['balance_amount'])==-10
refund=a.call('refunds',dict(client_id=f['client_id'],amount='10',method='cash',reason='QA accountant UI confirmation'),201)
f['refund_id']=refund['id'];(OUT/'mvp-final-ui-fixture.json').write_text(json.dumps(f),encoding='utf-8');print(refund['id'])
