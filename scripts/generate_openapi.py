"""Generate the local application's complete route inventory and wire schemas.

Run with backend/.venv/Scripts/python.exe scripts/generate_openapi.py.
No database connection or application data is used.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()
from django.db import models
from shop import models as domain

S = {'type': 'string'}
U = {'type': 'string', 'format': 'uuid'}
I = {'type': 'integer', 'minimum': 0}
B = {'type': 'boolean'}
D = {'type': 'string', 'format': 'date'}
DT = {'type': 'string', 'format': 'date-time'}
M = {'type': 'string', 'pattern': r'^-?\d+(\.\d{1,2})?$', 'example': '1500.00', 'description': 'Decimal KZT amount; never a binary floating-point value.'}

def ref(name): return {'$ref': '#/components/schemas/' + name}
def arr(item): return {'type': 'array', 'items': item}
def obj(props=None, required=(), extra=True):
    result = {'type': 'object', 'properties': props or {}, 'additionalProperties': extra}
    if required: result['required'] = list(required)
    return result
def enum(*items): return {'type': 'string', 'enum': list(items)}

schemas = {}
for name in ['Client', 'Product', 'Batch', 'Quota', 'LedgerEntry', 'Payment', 'Refund', 'ReturnRequest', 'AuditEvent', 'Notification', 'Handover', 'Shift', 'CashMovement', 'StockMovement', 'Period', 'WeeklyReport', 'DeliveryPoint']:
    props = {}
    for field in getattr(domain, name)._meta.concrete_fields:
        base = field.target_field if isinstance(field, models.ForeignKey) else field
        value = (DT if isinstance(base, models.DateTimeField) else D if isinstance(base, models.DateField) else
                 B if isinstance(base, models.BooleanField) else M if isinstance(base, models.DecimalField) else
                 U if isinstance(base, models.UUIDField) else {'type': 'integer'} if isinstance(base, models.IntegerField) else
                 {} if isinstance(base, models.JSONField) else S)
        props[field.attname] = {**value, **({'nullable': True} if field.null else {})}
    schemas[name] = obj(props)

schemas.update({
 'Problem': obj({'code': S, 'message': S, 'field_errors': {'type': 'object', 'additionalProperties': arr(S)}, 'details': {'nullable': True}, 'request_id': U}, ['code', 'message', 'field_errors', 'request_id']),
 'Identity': obj({'user_id': U, 'role': enum('admin','accountant','cashier','courier','customer'), 'client_id': {**U,'nullable':True}, 'name':S,'phone':S,'client_name':S,'approval_status':enum('pending','active','rejected'),'must_change_password':B}),
 'Staff': obj({'id':U,'name':S,'phone':S,'role':S,'is_active':B,'must_change_password':B}),
 'Photo': obj({'id':U,'order_id':U,'purpose':enum('delivery','cash','return','exchange','payment'),'mime':S,'size':I,'created_at':DT,'url':S,'expires_in':I}),
 'OrderItem': obj({'product_id':U,'name':S,'unit':S,'quantity':I,'delivered_quantity':I,'returned_quantity':I,'unit_price_amount':M,'line_total_amount':M}),
 'Order': obj({'id':U,'client_id':U,'client_name':S,'kind':enum('regular','preorder'),'status':S,'payment_mode':enum('deferred','cash','kaspi'),'total_amount':M,'delivered_amount':M,'paid_amount':M,'outstanding_amount':M,'created_at':DT,'requested_delivery_at':DT,'payment_due_at':{**D,'nullable':True},'version':I,'items':arr(ref('OrderItem')),'events':arr(ref('AuditEvent')),'photos':arr(ref('Photo'))}),
 'CatalogItem': obj({'id':U,'name':S,'description':S,'image_url':S,'shelf_life_hours':I,'price_amount':M,'available_qty':I,'preorder_available_qty':I,'preparation_minutes':I,'available_dates':arr(D),'batches':arr(obj({'id':I,'available_qty':I,'manufactured_at':DT,'expires_at':DT}))}),
 'Balance': obj({'currency':enum('KZT'),'balance_amount':M,'debt_amount':M,'advance_amount':M,'overdue_amount':M,'reserved_credit_amount':M,'credit_limit_amount':M,'available_credit_amount':M,'period_days':I,'period_start':D,'period_end_exclusive':D,'items':arr(ref('Client'))}),
 'Report': obj({'from':D,'to':D,'cutoff':DT,'generated_at':DT,'items':arr(ref('LedgerEntry')),'next_cursor':{**S,'nullable':True},'totals':obj({'turnover_amount':M,'delivered_amount':M,'paid_amount':M,'debt_amount':M,'advance_amount':M,'return_credit_amount':M,'refund_amount':M,'net_amount':M}),'groups':arr(obj())}),
 'Profile': obj({'profile':obj({'name':S,'contact_name':S,'phone':S,'category':S,'description':S,'approval_status':S,'deferred_approved':B,'archived':B,'period_days':I,'credit_limit_amount':M}),'balance':obj({'debt_amount':M,'advance_amount':M,'overdue_amount':M,'unconfirmed_payment_amount':M,'reserved_refund_amount':M}),'period':obj({'delivered_amount':M,'return_credit_amount':M,'turnover_amount':M,'paid_amount':M,'refund_amount':M,'outstanding_amount':M}),'from':D,'to':D,'generated_at':DT,'currency':enum('KZT')}),
 'Invitation': obj({'id':U,'invitation_token':S,'expires_in':I,'must_change_password':B}),
 'PaymentInstructions': obj({'method':enum('kaspi'),'seller_url':{**S,'nullable':True},'configured':B,'reference_required':B,'proof_required':B,'instructions':S}),
})
for name in list(schemas):
    if name not in ['Problem','Identity','Invitation']:
        schemas[name+'Page'] = obj({'items':arr(ref(name)),'next_cursor':{**S,'nullable':True}},['items','next_cursor'])

paths = {}
pagination = [{'name':'limit','in':'query','schema':{'type':'integer','minimum':1,'maximum':100}}, {'name':'cursor','in':'query','schema':S,'description':'Opaque signed continuation from next_cursor; keep filters unchanged.'}]
csrf = {'name':'X-CSRFToken','in':'header','required':True,'schema':S}
idem = {'name':'Idempotency-Key','in':'header','required':True,'schema':U,'description':'Reuse this UUID after an ambiguous network/server failure; new payload requires a new key.'}

def endpoint(path, method, summary, roles='authenticated', response=None, props=None, required=(), page=False, public=False, code=200, queries=None):
    params=[]
    for part in path.split('/'):
        if part.startswith('{'):
            params.append({'name':part[1:-1],'in':'path','required':True,'schema':S,'description':'Persisted resource identifier.'})
    if page: params += pagination
    for name, schema in (queries or {}).items(): params.append({'name':name,'in':'query','schema':schema})
    if method=='post':
        params.append(csrf)
        if not path.startswith('/auth/'): params.append(idem)
    result={'summary':summary,'operationId':method+'_'+path.strip('/').replace('/','_').replace('{','').replace('}','').replace('-','_'),
            'description':'Roles: '+roles+'.','parameters':params,'responses':{str(code):{'description':'Success'}}, 'x-roles':roles.split(',')}
    if public: result['security']=[]
    if response: result['responses'][str(code)]['content']={'application/json':{'schema':ref(response)}}
    if method=='post': result['requestBody']={'required':True,'content':{'application/json':{'schema':obj(props,required)}}}
    for status in ['401','403','404','409','422','429']:
        result['responses'][status]={'description':{'401':'Authentication required','403':'Role or client access denied','404':'Resource missing or outside object scope','409':'State, stock, price, version, balance or idempotency conflict','422':'Input validation; field_errors identifies fields','429':'Rate limited'}[status],'content':{'application/json':{'schema':ref('Problem')}}}
    paths.setdefault(path,{})[method]=result

endpoint('/auth/csrf','get','Set CSRF cookie',public=True,code=204)
endpoint('/auth/login','post','Create session',public=True,response='Identity',props={'phone':S,'password':S},required=['phone','password'])
endpoint('/auth/register','post','Apply as a new client organization',public=True,response='Identity',code=201,props={'phone':S,'password':S,'name':S,'category':enum('coffee_shop','store','restaurant','company','individual','other'),'category_other':S,'description':S,'expected_order_quantity':I,'expected_order_frequency':S,'preferred_payment_mode':enum('cash','kaspi','deferred'),'requested_period_days':{'type':'integer','enum':[7,14,30]}},required=['phone','password','name','category','description','expected_order_quantity','expected_order_frequency'])
endpoint('/auth/me','get','Current session identity',response='Identity')
endpoint('/auth/logout','post','End session',code=204)
for path in ['/auth/activate','/auth/accept-invitation']:
    endpoint(path,'post','Set first password using a single-use invitation',public=True,props={'token':S,'password':S},required=['token','password'])
endpoint('/auth/change-password','post','Set new password using reset token or current password',public=True,props={'token':S,'current_password':S,'password':S},required=['password'])
endpoint('/profile','get','Own organization profile and financial/purchase summary','customer','Profile',queries={'from':D,'to':D})
endpoint('/catalog','get','Available catalogue with dates, stock and product details','customer,admin,cashier,accountant','CatalogItemPage',page=True,queries={'delivery_date':D})
endpoint('/balance','get','Authoritative balance and overdue calculation','customer,admin,cashier,accountant','Balance',queries={'client_id':U})
endpoint('/payment-instructions','get','Configured seller link and manual payment instructions',response='PaymentInstructions')

for path,name,roles in [('/delivery-points','DeliveryPoint','admin,customer'),('/staff','Staff','admin,cashier,accountant'),('/clients','Client','admin,cashier,accountant'),('/products','Product','admin,cashier,accountant'),('/batches','Batch','admin,cashier,accountant'),('/quotas','Quota','admin,cashier,accountant'),('/payments','Payment','customer,admin,courier,cashier,accountant'),('/ledger','LedgerEntry','customer,admin,cashier,accountant'),('/periods','Period','customer,admin,accountant'),('/cash-movements','CashMovement','admin,courier,cashier,accountant'),('/handovers','Handover','admin,courier,cashier,accountant'),('/shifts','Shift','admin,cashier,accountant'),('/returns','ReturnRequest','customer,admin,courier,cashier,accountant'),('/refunds','Refund','admin,cashier,accountant'),('/stock-movements','StockMovement','admin,accountant'),('/audit','AuditEvent','admin,accountant'),('/notifications','Notification','authenticated')]:
    queries={'client_id':U} if path in ['/delivery-points','/payments','/ledger'] else {}
    if path=='/notifications': queries={'after':DT}
    if path=='/ledger':queries.update({'from':D,'to':D})
    endpoint(path,'get','List '+name+' records within role scope',roles,name+'Page',page=True,queries=queries)

order_props={'client_id':U,'kind':enum('regular','preorder'),'delivery_point_id':U,'requested_delivery_at':DT,'payment_mode':enum('cash','kaspi','deferred'),'items':arr(obj({'product_id':U,'quantity':{'type':'integer','minimum':1,'maximum':10000},'expected_unit_price':M},['product_id','quantity','expected_unit_price'],False)),'exchange_id':U}
endpoint('/orders','get','List visible orders','customer,admin,courier,cashier,accountant','OrderPage',page=True,queries={'status':S,'client_id':U,'search':S,'from':D,'to':D})
endpoint('/orders','post','Reserve stock and create order; does not accrue debt','customer,admin','Order',order_props,['kind','delivery_point_id','requested_delivery_at','payment_mode','items'],code=201)
endpoint('/orders/{id}','get','Full order, events and private photo metadata','customer,admin,courier,cashier,accountant','Order')
quantity_items=arr(obj({'product_id':U,'quantity':I},['product_id','quantity']))
for action,roles,props,required in [
 ('transition','customer,admin,courier',{'status':S,'version':I,'courier_id':U,'reason':S},['status','version']),
 ('fulfill','admin',{'version':I,'batches':arr(obj({'batch_id':I,'product_id':U,'quantity':I}))},['batches']),
 ('delivery','admin,courier',{'version':I,'items':quantity_items,'photo_ids':arr(U),'reason':S,'cash_received_amount':M,'cash_change_amount':M,'advance_consent':B},['version','items','photo_ids']),
 ('delivery-failed','admin,courier',{'version':I,'reason':S},['version','reason']),
 ('reschedule','admin',{'version':I,'requested_delivery_at':DT,'reason':S},['requested_delivery_at','reason']),
 ('reschedule-confirm','customer',{'version':I,'accept':B},['accept']),
 ('payment-mode','admin',{'version':I,'payment_mode':enum('deferred'),'reason':S},['version','payment_mode','reason']),
 ('assign-collection','admin',{'courier_id':U,'reason':S},['courier_id','reason']),
 ('goods-return','admin',{'items':quantity_items,'reason':S},['items','reason'])]:
    endpoint('/orders/{id}/'+action,'post','Order: '+action,roles,'Order',props,required)

endpoint('/delivery-points','post','Create delivery point','admin,customer','DeliveryPoint',{'client_id':U,'address':S,'recipient':S,'phone':S,'window_start':S,'window_end':S},['address','recipient','phone'],code=201)
endpoint('/staff','post','Invite employee','admin','Invitation',{'name':S,'phone':S,'role':enum('admin','courier','cashier','accountant')},['name','phone','role'],code=201)
endpoint('/staff/{id}/role','post','Change role and revoke existing sessions','admin','Staff',{'role':enum('admin','courier','cashier','accountant')},['role'])
endpoint('/staff/{id}/reset-access','post','Invalidate password/sessions and issue reset token','admin','Invitation')
endpoint('/clients/{id}/members','get','List organization members','admin','StaffPage',page=True)
endpoint('/clients/{id}/members','post','Invite another employee of an existing client','admin','Invitation',{'phone':S,'name':S},['phone','name'],code=201)
endpoint('/clients/{id}/approve','post','Set access and deferred credit independently','admin','Client',{'approval_status':enum('pending','active','rejected'),'deferred_approved':B,'credit_limit':M,'credit_limit_amount':M,'period_days':{'type':'integer','enum':[7,14,30]},'period_start':D})
product_props={'name':S,'description':S,'image_url':S,'shelf_life_hours':I,'price_amount':M,'preparation_minutes':I,'active':B}
endpoint('/products','post','Create product','admin','Product',product_props,['name','price_amount'],code=201)
endpoint('/catalog','post','Create product (compatibility alias)','admin','Product',product_props,['name','price_amount'],code=201)
endpoint('/products/{id}/update','post','Edit product and price','admin','Product',product_props)
endpoint('/products/{id}','post','Edit full product metadata and price','admin','Product',product_props)
for resource,model in [('products','Product'),('clients','Client')]:
    for action in ['archive','restore']:
        endpoint('/'+resource+'/{id}/'+action,'post',action.title()+' while preserving history','admin',model)
endpoint('/batches','post','Create actual stock batch','admin','Batch',{'product_id':U,'quantity':I,'manufactured_at':DT,'expires_at':DT},['product_id','quantity','manufactured_at','expires_at'],code=201)
endpoint('/quotas','post','Create production quota','admin','Quota',{'product_id':U,'quantity':I,'date':D,'cutoff':DT},['product_id','quantity','date','cutoff'],code=201)
endpoint('/batches/{id}/adjust','post','Adjust unreserved stock with reason','admin','Batch',{'quantity':I,'reason':S},['quantity','reason'])
endpoint('/payments','post','Submit Kaspi proof or record authorized cash receipt','customer,admin,courier,cashier,accountant','Payment',{'client_id':U,'order_id':U,'method':enum('cash','kaspi'),'amount':M,'reference':S,'proof_id':U,'photo_ids':arr(U),'cash_received_amount':M,'cash_change_amount':M,'advance_consent':B},['method','amount'],code=201)
for action,roles,required in [('confirm','admin,cashier,accountant',()),('reject','admin,cashier,accountant',['reason']),('reverse','admin,accountant',['reason'])]:
    endpoint('/payments/{id}/'+action,'post',action.title()+' payment; admin Kaspi confirmation requires reason',roles,'Payment',{'reason':S,'reference':S},required)
endpoint('/periods/close','post','Close completed financial periods','admin,accountant',props={'as_of':D})
for path in ['/cash','/cash-balance']:
    endpoint(path,'get','Courier cash and reserved handovers','admin,cashier,accountant,courier',queries={'courier_id':U})
endpoint('/cash-movements','post','Issue or return courier float','admin,cashier','CashMovement',{'courier_id':U,'direction':enum('issue','return'),'amount':M,'reason':S},['courier_id','direction','amount','reason'],code=201)
endpoint('/handovers','post','Reserve courier cash for handover','courier','Handover',{'amount':M},['amount'],code=201)
for action in ['confirm','reject']:
    endpoint('/handovers/{id}/'+action,'post',action.title()+' cash handover; difference requires reason','admin,cashier','Handover',{'amount':M,'reason':S},['reason'] if action=='reject' else ())
endpoint('/shifts','post','Open or close cashier shift; discrepancy requires reason','admin,cashier','Shift',{'action':enum('open','close'),'opening_amount':M,'counted_amount':M,'reason':S},['action'])
endpoint('/returns','post','Request return/exchange of delivered quantities','customer,admin,courier','ReturnRequest',{'order_id':U,'kind':enum('return','exchange'),'items':quantity_items,'reason':S,'photo_ids':arr(U)},['order_id','items','reason','photo_ids'],code=201)
endpoint('/returns/{id}/receive','post','Receive returned goods into quarantine','admin,courier','ReturnRequest',{'photo_ids':arr(U)},['photo_ids'])
endpoint('/returns/{id}/decide','post','Approve or reject return','admin','ReturnRequest',{'decision':enum('approve','reject'),'reason':S,'disposition':enum('quarantine','write_off'),'without_collection':B},['decision','reason'])
endpoint('/refunds','post','Create refund obligation from available advance','admin,cashier,accountant','Refund',{'client_id':U,'amount':M,'method':enum('cash','kaspi'),'reason':S},['client_id','amount','method','reason'],code=201)
endpoint('/refunds/{id}/confirm','post','Confirm actual money refund','admin,cashier,accountant','Refund')
endpoint('/stock-movements/{id}/resolve','post','Resolve quarantine','admin','StockMovement',{'disposition':enum('available','write_off'),'batch_id':I,'reason':S},['disposition','reason'])
endpoint('/notifications/{id}/read','post','Mark own notification read')
endpoint('/reports','get','Turnover, payments and balances as separate measures','customer,admin,courier,cashier,accountant','Report',page=True,queries={'from':D,'to':D,'client_id':U,'cutoff':DT,'group':enum('weekly'),'format':enum('json','csv')})
paths['/reports']['get']['responses']['200']['content']['text/csv']={'schema':S}
for path in ['/weekly-reports','/reports/weekly']:
    endpoint(path,'get','Saved weekly report snapshots','customer,admin,accountant','WeeklyReportPage',page=True,queries={'client_id':U})
endpoint('/files','post','Upload sanitized private photos (1–5, JPEG/PNG/WebP, at most 10 MB each)','customer,admin,courier,cashier,accountant','PhotoPage',code=201)
paths['/files']['post']['requestBody']={'required':True,'content':{'multipart/form-data':{'schema':obj({'order_id':U,'purpose':enum('delivery','cash','return','exchange','payment'),'files':arr({'type':'string','format':'binary'})},['order_id','purpose','files'])}}}
endpoint('/files/{id}','get','Get private photo metadata and 5-minute user-bound content URL',response='Photo')
endpoint('/files/{id}/content','get','Read private photo; authenticated session and signed token required',queries={'token':S})
paths['/files/{id}/content']['get']['responses']['200']['content']={'image/jpeg':{'schema':{'type':'string','format':'binary'}},'image/png':{'schema':{'type':'string','format':'binary'}},'image/webp':{'schema':{'type':'string','format':'binary'}}}
for path in ['/live','/ready']:
    endpoint(path,'get','Process liveness' if path=='/live' else 'Database and migration readiness',public=True)
    paths[path]['get']['servers']=[{'url':'/'}]
    if path=='/ready': paths[path]['get']['responses']['503']={'description':'Database unavailable or migrations pending'}

document={'openapi':'3.0.3','info':{'title':'Кондитерская — локальный API','version':'0.3.0','description':'Session + CSRF. All financial amounts are decimal KZT strings, timestamps RFC3339. Business writes require Idempotency-Key. Organization and courier object scoping is enforced server-side. Kaspi is manually verified: a proof is never automatic confirmation. Cursors are opaque and must be used with unchanged filters. Property-level validation is described by field_errors; conditional validation is enforced by each workflow.'},'servers':[{'url':'/api/v1'}],'security':[{'sessionAuth':[]}],'paths':paths,'components':{'securitySchemes':{'sessionAuth':{'type':'apiKey','in':'cookie','name':'sessionid'}},'schemas':schemas}}
(ROOT/'docs/openapi.yaml').write_text(json.dumps(document,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Generated {len(paths)} paths, {sum(len(p) for p in paths.values())} operations, {len(schemas)} schemas')
