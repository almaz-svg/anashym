"""Deactivate only explicitly tracked QA products; preserve business history."""
import json
from mvp_http import Session,OUT
s=Session('http://127.0.0.1:8000');s.login('+77010000002','DemoAdmin2026!');ids=json.loads((OUT/'mvp-created-products.json').read_text());results=[]
for pid in dict.fromkeys(ids):
 try:r=s.call('products/'+pid+'/update',dict(active=False,reason='QA finished: hide isolated fixture from live catalog'));results.append(dict(id=pid,inactive=r.get('active') is False))
 except Exception as e:results.append(dict(id=pid,error=str(e)))
(OUT/'mvp-cleanup-results.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print('Tracked QA products',len(results),'deactivated',sum(x.get('inactive',False) for x in results))
