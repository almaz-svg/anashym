"""Bounded read load including visible-cabinet 1s notification polling.

No synthetic data is created. Results describe the measured dataset, never imply
100k/500k volume unless a separate benchmark fixture was actually loaded.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import http.cookiejar
import http.client
import json
import math
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from datetime import datetime
from zoneinfo import ZoneInfo


def session(base,phone,password):
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    opener.open(base+'/auth/csrf',timeout=20).read()
    csrf = next(c.value for c in cookies if c.name=='csrftoken')
    request = urllib.request.Request(base+'/auth/login',data=json.dumps({'phone':phone,'password':password}).encode(),
        headers={'Content-Type':'application/json','X-CSRFToken':csrf},method='POST')
    opener.open(request,timeout=20).read()
    opener._qa_cookies=cookies
    return opener


def main(args):
    openers = []
    # Set up sessions before measurement: PBKDF password work isn't a read latency.
    for _ in range(args.clients):
        openers.append(session(args.base,args.phone,args.password))
    day = datetime.now(ZoneInfo('Asia/Almaty')).date().isoformat()
    paths = ['/notifications','/orders?limit=20','/catalog?delivery_date='+day,'/balance']
    def user(index_and_opener):
        index,opener=index_and_opener
        time.sleep(args.stagger_seconds*index/args.clients)
        samples = []
        target=urlsplit(args.base)
        connection=(http.client.HTTPSConnection if target.scheme=='https' else http.client.HTTPConnection)(target.hostname,target.port,timeout=30)
        headers={'Cookie':'; '.join(cookie.name+'='+cookie.value for cookie in opener._qa_cookies)}
        for tick in range(args.seconds):
            due = time.monotonic() + 1
            for path in (paths[0],paths[1+(tick%3)]):
                started = time.monotonic()
                transport_error = None
                try:
                    connection.request('GET',target.path.rstrip('/')+path,headers=headers)
                    response = connection.getresponse()
                    response.read()
                    status = response.status
                except urllib.error.HTTPError as exc:
                    status = exc.code
                except (OSError,http.client.HTTPException) as exc:
                    status = 0
                    transport_error = str(exc)
                    connection.close()
                samples.append({'path':path,'milliseconds':round((time.monotonic()-started)*1000,3),'status':status,'transport_error':transport_error})
            time.sleep(max(0,due-time.monotonic()))
        connection.close()
        return samples
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.clients) as executor:
        samples = [sample for batch in executor.map(user,enumerate(openers)) for sample in batch]
    values = sorted(sample['milliseconds'] for sample in samples)
    result = {'clients':args.clients,'duration_seconds':round(time.monotonic()-started,3),'requests':len(samples),
              'errors':sum(sample['status']!=200 for sample in samples),
              'p95_read_ms':values[math.ceil(len(values)*.95)-1],
              'mean_read_ms':round(statistics.mean(values),3),'dataset_note':args.dataset_note,
              'http_connection_reuse':True,
              'start_stagger_seconds':args.stagger_seconds,
              'notification_polling':'1 second per visible cabinet','samples':samples}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:value for key,value in result.items() if key!='samples'},ensure_ascii=False))


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base',default='http://127.0.0.1:8000/api/v1')
    parser.add_argument('--phone',default='+77010000001')
    parser.add_argument('--password',default='DemoClient2026!')
    parser.add_argument('--clients',type=int,default=50)
    parser.add_argument('--seconds',type=int,default=10)
    parser.add_argument('--stagger-seconds',type=float,default=0,help='0=synchronized start; 1=evenly spread client start over one second')
    parser.add_argument('--output',default='qa/load-results.json')
    parser.add_argument('--dataset-note',default='Existing local demo dataset; not 100000 orders/500000 items')
    args = parser.parse_args()
    if not 1<=args.clients<=50 or not 1<=args.seconds<=60:
        parser.error('clients 1..50, seconds 1..60')
    if not 0<=args.stagger_seconds<=1:
        parser.error('stagger-seconds 0..1')
    main(args)
