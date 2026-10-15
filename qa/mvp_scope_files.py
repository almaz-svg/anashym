"""Actual HTTP cashier settlement scope and private photo validation."""
import io,json,uuid
from PIL import Image
from mvp_http import Session,check,RESULTS,OUT

def run():
 base='http://127.0.0.1:8000';a=Session(base);a.login('+77010000002','DemoAdmin2026!')
 f=json.loads((OUT/'mvp-ui-fixture.json').read_text());customer=Session(base);customer.login(f['phone'],f['password'])
 def cashier():
  phone='+775'+str(uuid.uuid4().int)[:8];who=a.call('staff',dict(phone=phone,name='QA settlement '+uuid.uuid4().hex[:6],role='cashier'),201);s=Session(base);s.call('auth/csrf',expected=204);s.call('auth/accept-invitation',dict(token=who['invitation_token'],password='QaScopeStaff2026!'));s.login(phone,'QaScopeStaff2026!');return s
 c1,c2=cashier(),cashier()
 payment=customer.call('payments',dict(method='kaspi',amount='1',reference='QA-SCOPE-'+uuid.uuid4().hex),201)
 check('cashier unreviewed Kaspi visible for reconciliation',payment['id'] in [p['id'] for p in c2.call('payments')['items']])
 c1.call('payments/'+payment['id']+'/confirm',dict(reason='QA own reconciliation'))
 check('confirming cashier retains own confirmed payment',payment['id'] in [p['id'] for p in c1.call('payments')['items']])
 check('another cashier cannot see foreign confirmed settlement',payment['id'] not in [p['id'] for p in c2.call('payments')['items']])
 for c,label in [(c1,'own'),(c2,'foreign')]:
  report=c.call('reports?client_id='+f['client_id']);exists=any(x.get('reference')=='payment:'+payment['id'] for x in report['items']);check('cashier report '+label+' settlement scope',exists==(label=='own'))
 def upload(contents,expected=201):
  boundary='QA'+uuid.uuid4().hex;raw=b''
  for name,value in [('order_id',f['cash_order']),('purpose','payment')]:raw+=f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
  for index,content in enumerate(contents):raw+=f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="qa{index}.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode()+content+b'\r\n'
  raw+=f'--{boundary}--\r\n'.encode();return customer.call('files',raw=raw,content_type='multipart/form-data; boundary='+boundary,expected=expected)
 upload([b'not a photo'],422);check('invalid image bytes return structured422',True)
 import base64
 broken=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/l9sAAAAASUVORK5CYII=')
 upload([broken],422);check('broken PNG checksum returns422 rather than500',True)
 exif=Image.Exif();exif[270]='QA metadata must be removed';buffer=io.BytesIO();Image.new('RGB',(24,24),(40,80,120)).save(buffer,format='JPEG',exif=exif);content=buffer.getvalue()
 result=upload([content]*6,None)
 denied=customer.last_status in [400,422]
 RESULTS.append(dict(name='upload six photos returns structured validation',pass_=denied and isinstance(result,dict) and 'code' in result,detail={'status':customer.last_status,'json':isinstance(result,dict)}))
 print('PASS' if RESULTS[-1]['pass_'] else 'FAIL','upload six photos returns structured validation',RESULTS[-1]['detail'])
 file=upload([content])['items'][0];metadata=customer.call('files/'+file['id']);route=metadata['url'].split('/api/v1/')[1];private=customer.call(route)
 check('private content removes EXIF',not Image.open(io.BytesIO(private)).getexif())
 cache=next((v for k,v in customer.last_headers.items() if k.lower()=='cache-control'),'');check('private stream forbids shared caching',cache=='private, no-store')
 anon=Session(base);anon.call(route,expected=401);check('anonymous signed link denied',True)
 foreign=Session(base);foreign.login('+77010000001','DemoClient2026!');foreign.call(route,expected=404);check('foreign customer signed link denied',True)
 # Same photo but another authorized user's signed URL must not replay across identities.
 a.call(route,expected=403);check('signed URL bound to requesting user',True)
 customer.call('files/'+file['id']+'/content?token=tampered',expected=403);check('tampered signature denied',True)

if __name__=='__main__':
 try:run()
 except Exception as e:RESULTS.append(dict(name='runner failure',pass_=False,detail=str(e)));raise
 finally:(OUT/'mvp-scope-files-results.json').write_text(json.dumps(RESULTS,ensure_ascii=False,indent=2),encoding='utf-8')
