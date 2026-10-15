"""Real PostgreSQL application HTTP races, separate session per concurrent request."""
import json,uuid,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from mvp_http import Session,check,OUT,RESULTS

def run():
 base='http://127.0.0.1:8000';admin=Session(base);admin.login('+77010000002','DemoAdmin2026!');now=datetime.now(timezone.utc);day=datetime.now(timezone(timedelta(hours=5))).date()
 def customer(limit):
  phone='+774'+str(uuid.uuid4().int)[:8];s=Session(base);s.call('auth/csrf',expected=204);me=s.call('auth/register',dict(phone=phone,password='QaParallel2026!',name='QA parallel '+uuid.uuid4().hex[:8],category='company',description='Independent actual HTTP concurrency',expected_order_quantity=10,expected_order_frequency='QA'),201)
  admin.call('clients/'+me['client_id']+'/approve',dict(approval_status='active',deferred_approved=True,credit_limit_amount=str(limit),period_days=7,reason='QA concurrency fixture'))
  s.login(phone,'QaParallel2026!');point=s.call('delivery-points',dict(address='QA parallel fixture',recipient='QA',phone=phone),201)['id'];sessions=[]
  for _ in range(6):p=Session(base);p.login(phone,'QaParallel2026!');sessions.append(p)
  return s,sessions,point
 def race(sessions,route,body):
  barrier=threading.Barrier(len(sessions))
  def request(s):
   barrier.wait();data=s.call(route,body,expected=None);return dict(status=s.last_status,response=data)
  with ThreadPoolExecutor(max_workers=len(sessions)) as pool:return list(pool.map(request,sessions))
 for mode in ['stock','quota','credit']:
  c,sessions,point=customer(6000 if mode=='credit' else 100000)
  p=admin.call('products',dict(name='QA parallel '+mode+' '+uuid.uuid4().hex[:6],price_amount='1500',description='Concurrency only',preparation_minutes=1),201)['id'];ids=json.loads((OUT/'mvp-created-products.json').read_text());ids.append(p);(OUT/'mvp-created-products.json').write_text(json.dumps(ids))
  target=day+timedelta(days=1) if mode=='quota' else day
  if mode=='quota':source=admin.call('quotas',dict(product_id=p,date=str(target),cutoff=(now+timedelta(hours=12)).isoformat(),quantity=6),201)
  else:source=admin.call('batches',dict(product_id=p,manufactured_at=(now-timedelta(hours=1)).isoformat(),expires_at=(now+timedelta(days=5)).isoformat(),quantity=100 if mode=='credit' else 6),201)
  body=dict(kind='preorder' if mode=='quota' else 'regular',delivery_point_id=point,requested_delivery_at=str(target)+'T18:00:00+05:00',payment_mode='deferred',items=[dict(product_id=p,quantity=2,expected_unit_price='1500')])
  results=race(sessions,'orders',body);success=[x for x in results if x['status']==201];expected=2 if mode=='credit' else 3
  check('PostgreSQL concurrent '+mode+' bounded successful orders',len(success)==expected and all(x['status'] in [201,409] for x in results),[dict(status=x['status'],code=x['response'].get('code')) for x in results])
  reserve=Decimal(c.call('balance')['reserved_credit_amount']);check('PostgreSQL '+mode+' exact reserved credit',reserve==expected*3000,str(reserve))
  for x in success:
   o=x['response'];admin.call('orders/'+o['id']+'/transition',dict(status='cancelled',version=o['version'],reason='QA cleanup isolated concurrent reservation'))
  check(mode+' cleanup releases reserve',Decimal(c.call('balance')['reserved_credit_amount'])==0)
 # Separate isolated courier wallet race.
 phone='+773'+str(uuid.uuid4().int)[:8];staff=admin.call('staff',dict(phone=phone,name='QA parallel courier',role='courier'),201);s=Session(base);s.call('auth/csrf',expected=204);s.call('auth/accept-invitation',dict(token=staff['invitation_token'],password='QaParallelStaff2026!'));s.login(phone,'QaParallelStaff2026!');other=Session(base);other.login(phone,'QaParallelStaff2026!')
 admin.call('cash-movements',dict(courier_id=staff['id'],amount='10000',direction='issue',reason='QA parallel float'),201)
 results=race([s,other],'handovers',dict(amount='7000'));check('PostgreSQL concurrent handover only one7000 reservation',sum(x['status']==201 for x in results)==1 and sum(x['status']==409 for x in results)==1)
 check('PostgreSQL handover available wallet3000',Decimal(s.call('cash')['available_amount'])==3000)
 for x in results:
  if x['status']==201:admin.call('handovers/'+x['response']['id']+'/reject',dict(reason='QA release parallel reservation'))
 admin.call('cash-movements',dict(courier_id=staff['id'],amount='10000',direction='return',reason='QA return isolated parallel float'),201)
 check('parallel courier wallet cleanupzero',Decimal(s.call('cash')['cash_amount'])==0)

if __name__=='__main__':
 try:run()
 except Exception as e:RESULTS.append(dict(name='runner failure',pass_=False,detail=str(e)));raise
 finally:(OUT/'mvp-concurrency-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
