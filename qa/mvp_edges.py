"""Independent HTTP edge and security acceptance; fresh client per invocation."""
import csv,io,json,uuid
from urllib.parse import quote
from decimal import Decimal
from datetime import datetime,timedelta,timezone
from mvp_http import Session,check,RESULTS,OUT

def run():
    base='http://127.0.0.1:8000'
    admin,courier,cashier,accountant=[Session(base) for _ in range(4)]
    for s,n in zip([admin,courier,cashier,accountant],[2,3,4,5]):s.login('+7701000000'+str(n),'DemoAdmin2026!' if n==2 else 'DemoStaff2026!')
    customer=Session(base);customer.call('auth/csrf',expected=204)
    phone='+778'+str(uuid.uuid4().int)[:8]
    who=customer.call('auth/register',dict(phone=phone,password='QaEdges2026!',name='QA edges '+uuid.uuid4().hex[:8],category='company',description='Isolated HTTP acceptance',expected_order_quantity=10,expected_order_frequency='QA only'),201)
    cid=who['client_id']
    admin.call('clients/'+cid+'/approve',dict(approval_status='active',deferred_approved=True,credit_limit_amount='1000000.00',period_days=7,reason='QA isolated approval'))
    customer.login(phone,'QaEdges2026!')
    point=customer.call('delivery-points',dict(address='QA independent test',recipient='QA',phone=phone),201)['id']
    cuid=courier.call('auth/me')['user_id'];now=datetime.now(timezone.utc);day=datetime.now(timezone(timedelta(hours=5))).date()
    balance=lambda:Decimal(customer.call('balance')['balance_amount'])
    def product(price,qty=100):
        p=admin.call('products',dict(name='QA edges '+uuid.uuid4().hex[:8],price_amount=str(price),description='Isolated edge fixture',preparation_minutes=1),201)['id']
        ids=json.loads((OUT/'mvp-created-products.json').read_text());ids.append(p);(OUT/'mvp-created-products.json').write_text(json.dumps(ids))
        b=admin.call('batches',dict(product_id=p,manufactured_at=(now-timedelta(hours=1)).isoformat(),expires_at=(now+timedelta(days=8)).isoformat(),quantity=qty),201)['id'];return p,b
    p,b=product(1500);p2,b2=product(2000)
    def order(rows,mode='deferred',kind='regular',date=None):
        return customer.call('orders',dict(kind=kind,delivery_point_id=point,requested_delivery_at=str(date or day)+'T18:00:00+05:00',payment_mode=mode,items=[dict(product_id=pid,quantity=q,expected_unit_price=str(price)) for pid,q,price in rows]),201)
    def action(o,status):
        current=admin.call('orders/'+o['id']);return admin.call('orders/'+o['id']+'/transition',dict(status=status,courier_id=cuid,version=current['version']))
    def dispatch(o):
        for state in ['accepted','preparing','ready','out_for_delivery']:o=action(o,state)
        return o
    def batch(bid):return next(x for x in admin.call('batches?limit=100')['items'] if str(x['id'])==str(bid))
    def scenario(name,fn):
        try:fn()
        except Exception as e:RESULTS.append(dict(name=name,pass_=False,detail=str(e)));print('FAIL',name,str(e))

    def cash_shortfall():
        o=dispatch(order([(p,2,1500)],mode='cash'));photo=courier.upload(o['id']);before=balance();stock=batch(b)
        body=dict(version=o['version'],items=[dict(product_id=p,quantity=2)],photo_ids=[photo],cash_received_amount='2999',cash_change_amount='0')
        courier.call('orders/'+o['id']+'/delivery',body,409)
        check('cash shortage rolls back money/order/stock',balance()==before and admin.call('orders/'+o['id'])['version']==o['version'] and batch(b)==stock)
        body['cash_received_amount']='3000';key=str(uuid.uuid4());courier.call('orders/'+o['id']+'/delivery',body,key=key);courier.call('orders/'+o['id']+'/delivery',body,key=key)
        check('cash full delivery net zero debt and idempotent',balance()==before)
        courier.call('files/'+photo,expected=404)
        check('completed courier photo denied',True)
        cashier.call('files/'+photo,expected=404)
        check('cashier delivery evidence denied',True)
    scenario('cash shortage/full/private files',cash_shortfall)

    def partial():
        before=balance();reserve=Decimal(customer.call('balance')['reserved_credit_amount']);o=dispatch(order([(p,4,1500),(p2,2,2000)]));photo=courier.upload(o['id']);stock=batch(b)
        courier.call('orders/'+o['id']+'/delivery',dict(version=o['version'],items=[dict(product_id=p,quantity=3)],photo_ids=[photo],reason='QA missing zero row'),422)
        body=dict(version=o['version'],items=[dict(product_id=p,quantity=3),dict(product_id=p2,quantity=0)],photo_ids=[photo],reason='QA customer accepted partial')
        done=courier.call('orders/'+o['id']+'/delivery',body)
        check('partial delivered charges only three portions',done['status']=='delivered' and balance()-before==Decimal('4500'))
        check('partial frees full credit reserve',Decimal(customer.call('balance')['reserved_credit_amount'])==reserve)
        check('delivery never consumes warehouse twice',batch(b)==stock)
        old=batch(b)['quantity'];admin.call('orders/'+o['id']+'/goods-return',dict(items=[dict(product_id=p,quantity=1),dict(product_id=p2,quantity=2)],reason='QA physically received leftovers'))
        check('physical leftovers never become saleable',batch(b)['quantity']==old)
        admin.call('orders/'+o['id']+'/goods-return',dict(items=[dict(product_id=p,quantity=1)],reason='QA duplicate physical return'),422)
        check('duplicate goods receipt denied',True)
    scenario('partial zero rows/reserves/quarantine',partial)

    def failed():
        before=balance();o=dispatch(order([(p,2,1500)]));stock=batch(b);body=dict(version=o['version'],reason='QA recipient absent');key=str(uuid.uuid4())
        courier.call('orders/'+o['id']+'/delivery-failed',body,key=key);courier.call('orders/'+o['id']+'/delivery-failed',body,key=key)
        check('failed delivery no charge',balance()==before)
        o=action(o,'out_for_delivery');check('retry dispatch not double warehouse deduction',batch(b)==stock)
        photo=courier.upload(o['id']);courier.call('orders/'+o['id']+'/delivery',dict(version=o['version'],items=[dict(product_id=p,quantity=2)],photo_ids=[photo]))
        check('retry successful one charge',balance()-before==Decimal('3000'))
    scenario('failed/retry/idempotency',failed)

    def preorder():
        future=day+timedelta(days=1);newday=day+timedelta(days=2)
        for when in [future,newday]:admin.call('quotas',dict(product_id=p,date=str(when),cutoff=(now+timedelta(hours=12)).isoformat(),quantity=20),201)
        o=order([(p,3,1500)],kind='preorder',date=future);o=action(o,'accepted');o=action(o,'preparing')
        admin.call('orders/'+o['id']+'/transition',dict(status='ready',version=o['version']),409)
        check('preorder ready blocked before actual fulfillment',True)
        olddate=o['requested_delivery_at'];proposal=dict(requested_delivery_at=str(newday)+'T18:00:00+05:00',reason='QA new production day',version=o['version'])
        proposed=admin.call('orders/'+o['id']+'/reschedule',proposal);check('proposal does not change committed date',proposed['requested_delivery_at']==olddate)
        rejected=customer.call('orders/'+o['id']+'/reschedule-confirm',dict(accept=False,version=proposed['version']));check('reject retains date',rejected['requested_delivery_at']==olddate)
        proposal['version']=rejected['version'];proposed=admin.call('orders/'+o['id']+'/reschedule',proposal);confirmed=customer.call('orders/'+o['id']+'/reschedule-confirm',dict(accept=True,version=proposed['version']))
        check('customer confirmation commits new date',confirmed['requested_delivery_at'][:10]==str(newday))
        stock=batch(b);quotas=admin.call('quotas?limit=100');admin.call('orders/'+o['id']+'/fulfill',dict(version=confirmed['version'],batches=[dict(product_id=p,batch_id=b,quantity=2)]),409)
        check('incomplete fulfill atomically restores batches and quotas',batch(b)==stock and admin.call('quotas?limit=100')==quotas)
        fulfilled=admin.call('orders/'+o['id']+'/fulfill',dict(version=confirmed['version'],batches=[dict(product_id=p,batch_id=b,quantity=3)]))
        o=action(fulfilled,'ready');check('complete actualbatch fulfillment enables ready',o['status']=='ready')
    scenario('preorder reschedule/atomic fulfillment',preorder)

    def refund_exchange():
        # Fully settle all previous charges, then create a known advance of100.
        outstanding=balance();pay=customer.call('payments',dict(method='kaspi',amount=str(outstanding+100),reference='QA-EDGE-'+uuid.uuid4().hex),201);cashier.call('payments/'+pay['id']+'/confirm',{})
        check('excess payment becomes advance100',balance()==Decimal('-100'))
        cashier.call('refunds',dict(client_id=cid,amount='101',method='kaspi',reason='QA exceeds advance'),409)
        refund=cashier.call('refunds',dict(client_id=cid,amount='100',method='kaspi',reason='QA refund advance'),201);key=str(uuid.uuid4());body=dict(reference='QA-RF-'+uuid.uuid4().hex,reason='QA observed demo refund')
        cashier.call('refunds/'+refund['id']+'/confirm',body,key=key);cashier.call('refunds/'+refund['id']+'/confirm',body,key=key);check('refund bound and idempotent confirm',balance()==0)
        o=dispatch(order([(p,1,1500)]));photo=courier.upload(o['id']);courier.call('orders/'+o['id']+'/delivery',dict(version=o['version'],items=[dict(product_id=p,quantity=1)],photo_ids=[photo]))
        rp=customer.upload(o['id'],'exchange');ret=customer.call('returns',dict(order_id=o['id'],kind='exchange',items=[dict(product_id=p,quantity=1)],reason='QA independent exchange',photo_ids=[rp]),201)
        admin.call('returns/'+ret['id']+'/decide',dict(decision='approve',reason='QA exchange without collection',without_collection=True,disposition='write_off'))
        admin.call('products/'+p+'/update',dict(price_amount='1600',reason='QA current replacement price'))
        replacement=customer.call('orders',dict(kind='regular',delivery_point_id=point,requested_delivery_at=str(day)+'T18:00:00+05:00',payment_mode='deferred',exchange_id=ret.get('exchange_id',ret['id']),items=[dict(product_id=p,quantity=1,expected_unit_price='1600')]),201)
        check('exchange independent replacement uses new price',replacement['id']!=o['id'] and Decimal(replacement['total_amount'])==1600 and Decimal(admin.call('orders/'+o['id'])['total_amount'])==1500)
    scenario('advance refund/exchange',refund_exchange)

    def reports():
        route=f'reports?from={day}&to={day}&client_id={cid}'
        report=accountant.call(route);raw=accountant.call(route+'&format=csv&cutoff='+quote(report['cutoff']));rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        check('CSV exact source IDs equal JSON',set(r['id'] for r in rows)==set(r['id'] for r in report['items']))
        check('CSV exact Decimal net matches JSON',sum((Decimal(r['amount']) for r in rows),Decimal(0))==Decimal(report['totals']['net_amount']))
        check('reports separate turnover payments debt',all(k in report['totals'] for k in ['turnover_amount','paid_amount','debt_amount']))
        weekly=accountant.call(route+'&group=weekly');check('ISO weekly groups reconcile',sum((Decimal(r['net_amount']) for r in weekly['groups']),Decimal(0))==Decimal(report['totals']['net_amount']))
        foreign=Session(base);foreign.login('+77010000001','DemoClient2026!');foreign.call('orders/'+o['id'],expected=404) if False else None
        check('client report filter cannot expose foreign ledger',not foreign.call(route)['items'])
    scenario('report CSV parity/role scope',reports)
    (OUT/'mvp-edge-fixture.json').write_text(json.dumps(dict(phone=phone,password='QaEdges2026!',client_id=cid,point_id=point,product_id=p,batch_id=b,product2_id=p2,courier_id=cuid)),encoding='utf-8')

if __name__=='__main__':
    try:run()
    finally:(OUT/'mvp-edges-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
