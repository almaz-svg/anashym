import json
from mvp_http import Session,OUT,check,RESULTS
try:
 for role,n,password in [('customer',1,'DemoClient2026!'),('admin',2,'DemoAdmin2026!'),('courier',3,'DemoStaff2026!'),('cashier',4,'DemoStaff2026!'),('accountant',5,'DemoStaff2026!')]:
  s=Session('http://127.0.0.1:8000');s.login('+7701000000'+str(n),password);check(role+' login role preserved after restart',s.call('auth/me')['role']==role)
  for route in ['orders?limit=1','payments?limit=1','notifications']:
   check(role+' '+route+' actual HTTP envelope',isinstance(s.call(route)['items'],list))
except Exception as e:
 RESULTS.append(dict(name='runner failure',pass_=False,detail=str(e)));raise
finally:(OUT/'mvp-final-smoke-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
