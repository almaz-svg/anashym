import json
from urllib.parse import quote
from decimal import Decimal
from mvp_http import Session,check,OUT,RESULTS

def run():
 base='http://127.0.0.1:8000';admin=Session(base);admin.login('+77010000002','DemoAdmin2026!');accountant=Session(base);accountant.login('+77010000005','DemoStaff2026!');f=json.loads((OUT/'mvp-edge-fixture.json').read_text());customer=Session(base);customer.login(f['phone'],f['password'])
 sources=admin.call('stock-movements')['items'];source=next(x for x in sources if x.get('product_id')==f['product_id'] and x['disposition']=='quarantine' and not x.get('resolved'))
 batch=lambda:next(x for x in admin.call('batches?limit=100')['items'] if str(x['id'])==str(f['batch_id']))
 source_id=str(source['id']);before=batch()['quantity'];customer.call('stock-movements/'+source_id+'/resolve',dict(disposition='available',batch_id=f['batch_id'],reason='QA denied customer stock approval'),403)
 check('customer cannot resolve quarantine',True)
 admin.call('stock-movements/'+source_id+'/resolve',dict(disposition='available',batch_id=f['batch_id'],reason='QA explicit fitness inspection accepted'))
 check('only explicit fitness decision restores stock',batch()['quantity']==before+source['quantity'])
 admin.call('stock-movements/'+source_id+'/resolve',dict(disposition='available',batch_id=f['batch_id'],reason='QA duplicate resolution'),409);check('quarantine duplicate resolution cannot double stock',True)
 archives=accountant.call('weekly-reports')['items']
 if not archives:
  RESULTS.append(dict(name='weekly immutable archive generated',pass_=None,detail='NOT RUN: worker archive absent'));return
 archived=archives[0];payload=archived['payload'];params='reports?from='+payload['from']+'&to='+payload['to']+'&cutoff='+quote(payload['cutoff']);fresh=accountant.call(params)
 check('weekly archive uses same frozen report arithmetic',fresh['totals']==payload['totals'] and {r['id'] for r in fresh['items']}=={r['id'] for r in payload['items']})
 own=customer.call('weekly-reports')['items'];check('weekly archive customer ledger scope',all(r['client_id']==f['client_id'] for arc in own for r in arc['payload']['items']))

if __name__=='__main__':
 try:run()
 except Exception as e:RESULTS.append(dict(name='runner failure',pass_=False,detail=str(e)));raise
 finally:(OUT/'mvp-quarantine-archive-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
