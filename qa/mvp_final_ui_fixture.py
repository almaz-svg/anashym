import json,uuid
from mvp_http import Session,OUT
a=Session('http://127.0.0.1:8000');a.login('+77010000002','DemoAdmin2026!')
f=json.loads((OUT/'mvp-ui-fixture.json').read_text())
a.call('products/'+f['product_id']+'/update',dict(active=True,reason='QA final UI isolated fixture'))
for role in ['cashier','courier']:
 phone='+772'+str(uuid.uuid4().int)[:8];staff=a.call('staff',dict(phone=phone,name='QA final UI '+role,role=role),201)
 s=Session('http://127.0.0.1:8000');s.call('auth/csrf',expected=204);s.call('auth/accept-invitation',dict(token=staff['invitation_token'],password='QaFinalUi2026!'))
 f[role+'_phone']=phone;f[role+'_id']=staff['id']
(OUT/'mvp-final-ui-fixture.json').write_text(json.dumps(f),encoding='utf-8')
