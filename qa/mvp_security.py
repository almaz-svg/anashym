"""Read-only and denied-write probes against actual application HTTP."""
import json
from mvp_http import Session, check, RESULTS, OUT

base='http://127.0.0.1:8000'
sessions={}
for role,n in [('customer',1),('admin',2),('courier',3),('cashier',4),('accountant',5)]:
    s=Session(base);s.login('+7701000000'+str(n),'DemoClient2026!' if n==1 else 'DemoAdmin2026!' if n==2 else 'DemoStaff2026!');sessions[role]=s
try:
    for role,s in sessions.items():
        for route in ['orders','payments','returns','notifications','cash','ledger','clients','audit']:
            denied=(route=='audit' and role not in ['admin','accountant']) or (route=='clients' and role in ['customer','courier']) or (route=='ledger' and role=='courier') or (route=='cash' and role=='customer')
            expected=403 if denied else 200
            try:
                result=s.call(route,expected=expected)
                check(role+' '+route+' permission',True)
            except AssertionError as e:
                RESULTS.append(dict(name=role+' '+route+' permission',pass_=False,detail=str(e)));print('FAIL',str(e))
    for role in ['customer','courier','cashier','accountant']:
        try: sessions[role].call('products',dict(name='forbidden QA',price_amount='1.00'),403);check(role+' create product denied',True)
        except AssertionError as e: RESULTS.append(dict(name=role+' create product denied',pass_=False,detail=str(e)))
finally:
    (OUT/'mvp-security-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
