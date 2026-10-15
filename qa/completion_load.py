"""Reproducible HTTP read/write acceptance against an isolated verification DB.

Never runs against confectionery. Creates synthetic clients, stock and orders,
starts its own hidden Waitress process and terminates only that process.
Background historical volume is reported, not assumed from fixture names.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as day_time, timedelta
import http.client
import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'backend'))
sys.path.insert(0, str(ROOT/'qa'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
from load_read import session


def stats(samples):
    times=sorted(row['ms'] for row in samples)
    return {'requests':len(times),'p50_ms':times[math.ceil(len(times)*.5)-1],
            'p95_ms':times[math.ceil(len(times)*.95)-1],'p99_ms':times[math.ceil(len(times)*.99)-1],
            'mean_ms':round(statistics.mean(times),3),'errors':sum(not row['ok'] for row in samples)}


def main(args):
    database=os.environ.get('DB_NAME','')
    if not args.confirm_isolated or not database.startswith('verify_'):
        raise SystemExit('Refusing: requires isolated DB_NAME=verify_<id> and --confirm-isolated')
    import django
    django.setup()
    from django.db import connection
    from django.utils import timezone
    from shop.models import Client, User, Product, Quota, DeliveryPoint, Order, OrderItem, Reservation, LedgerEntry

    run_id=uuid.uuid4().hex[:10]
    stamp=int(time.time())%100000000
    password='LoadOnly2026!'
    before={'orders':Order.objects.count(),'items':OrderItem.objects.count(),'ledger_entries':LedgerEntry.objects.count()}
    product=Product.objects.create(name='Load acceptance '+run_id,price='100.00',shelf_life_hours=72)
    day=timezone.localdate()+timedelta(days=1)
    requested=timezone.make_aware(datetime.combine(day,day_time(12,0)))
    quota=Quota.objects.create(product=product,date=day,cutoff=requested-timedelta(hours=1),quantity=args.clients*args.rounds+100)
    actors=[]
    for i in range(args.clients):
        org=Client.objects.create(name=f'Load {run_id} {i}',approval_status='active',deferred_approved=True,credit_limit='10000000.00',period_start=timezone.localdate())
        user=User.objects.create_user(username=f'+78{stamp:08d}{i:03d}',password=password,client=org,first_name='Synthetic load')
        point=DeliveryPoint.objects.create(client=org,address='Isolated benchmark',recipient='Synthetic',phone=user.username)
        actors.append({'id':str(user.pk),'client_id':str(org.pk),'phone':user.username,'point_id':str(point.pk)})
    connection.close()
    probe=socket.socket()
    try: probe.bind(('127.0.0.1',args.port))
    except OSError: raise SystemExit('Benchmark port already in use; refusing to replace another process')
    finally: probe.close()
    env=os.environ.copy()
    log_path=ROOT/f'qa/completion-load-{run_id}.server.log'
    output_path=ROOT/args.output
    with log_path.open('wb') as log:
        process=subprocess.Popen([sys.executable,'-m','config.serve','--host','127.0.0.1','--port',str(args.port),'--threads',str(args.threads)],cwd=ROOT/'backend',env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(100):
                if process.poll() is not None: raise RuntimeError('Benchmark server exited; inspect '+str(log_path))
                probe=socket.socket(); probe.settimeout(.1)
                try: probe.connect(('127.0.0.1',args.port)); break
                except OSError: time.sleep(.1)
                finally: probe.close()
            else: raise RuntimeError('Benchmark server did not start')
            base=f'http://127.0.0.1:{args.port}/api/v1'
            sessions=[]
            for actor in actors:
                opener=session(base,actor['phone'],password)
                sessions.append({'Cookie':'; '.join(c.name+'='+c.value for c in opener._qa_cookies),
                                 'X-CSRFToken':next(c.value for c in opener._qa_cookies if c.name=='csrftoken'),'Content-Type':'application/json'})
            def request(conn,headers,method,path,body=None,key=None):
                headers={**headers,**({'Idempotency-Key':key} if key else {})}
                started=time.perf_counter()
                try:
                    conn.request(method,'/api/v1'+path,body=json.dumps(body).encode() if body is not None else None,headers=headers)
                    response=conn.getresponse(); raw=response.read(); status=response.status
                    payload=json.loads(raw) if raw else {}
                except Exception as exc:
                    status=0; payload={'error':type(exc).__name__}; conn.close()
                return {'ms':round((time.perf_counter()-started)*1000,3),'status':status,'path':path,'ok':status in [200,201]},payload
            barrier=threading.Barrier(args.clients)
            def run_reader(index):
                conn=http.client.HTTPConnection('127.0.0.1',args.port,timeout=60)
                rows=[]; barrier.wait()
                for i in range(args.rounds):
                    for path in ['/notifications','/orders?limit=20','/catalog?delivery_date='+day.isoformat(),'/balance']:
                        row,_=request(conn,sessions[index],'GET',path); rows.append(row)
                conn.close(); return rows
            with ThreadPoolExecutor(max_workers=args.clients) as pool:
                reads=[row for result in pool.map(run_reader,range(args.clients)) for row in result]
            barrier=threading.Barrier(args.clients)
            def run_creator(index):
                conn=http.client.HTTPConnection('127.0.0.1',args.port,timeout=60)
                rows=[]; ids=[]; replay_checks=[]; barrier.wait()
                body={'kind':'preorder','delivery_point_id':actors[index]['point_id'],'requested_delivery_at':requested.isoformat(),'payment_mode':'deferred','items':[{'product_id':str(product.pk),'quantity':1,'expected_unit_price':'100.00'}]}
                for _ in range(args.rounds):
                    key=str(uuid.uuid4()); row,payload=request(conn,sessions[index],'POST','/orders',body,key)
                    rows.append(row)
                    if row['status']==201: ids.append(payload['id'])
                row,repeated=request(conn,sessions[index],'POST','/orders',body,key)
                replay_checks.append(row['status']==201 and repeated.get('id')==payload.get('id'))
                conn.close(); return rows,ids,replay_checks
            with ThreadPoolExecutor(max_workers=args.clients) as pool:
                creations=list(pool.map(run_creator,range(args.clients)))
            writes=[row for rows,_,_ in creations for row in rows]
            ids=[oid for _,batch,_ in creations for oid in batch]
            quota.refresh_from_db()
            org_ids=[a['client_id'] for a in actors]
            actual=Order.objects.filter(client_id__in=org_ids)
            invariants={'one_order_per_success':actual.count()==len(ids)==len(set(ids)),
                        'idempotent_replays':all(v for _,_,checks in creations for v in checks),
                        'reservation_matches_orders':quota.reserved==actual.count() and Reservation.objects.filter(quota=quota).count()==actual.count(),
                        'no_debt_before_handover':not LedgerEntry.objects.filter(client_id__in=org_ids).exists() and not Client.objects.filter(id__in=org_ids).exclude(balance=0).exists(),
                        'credit_matches_reservations':all(c.reserved_credit==actual.filter(client=c).count()*100 for c in Client.objects.filter(id__in=org_ids))}
            result={'database':database,'run_id':run_id,'environment':'Shared Windows developer laptop; CPU/RAM not restricted to 2vCPU/4GB',
                    'threads':args.threads,'clients':args.clients,'rounds':args.rounds,'connection_reuse':True,
                    'pattern':'Synchronized 50-session bursts without think time; 50 distinct organizations; shared quota serializes writes',
                    'background_dataset':before,'reads':stats(reads),'order_creation':stats(writes),'invariants':invariants,
                    'read_target_met':stats(reads)['p95_ms']<500 and stats(reads)['errors']==0,
                    'create_target_met':stats(writes)['p95_ms']<1000 and stats(writes)['errors']==0,
                    'samples':{'reads':reads,'orders':writes}}
            output_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in result.items() if k!='samples'},ensure_ascii=False))
        finally:
            process.terminate()
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--confirm-isolated',action='store_true')
    parser.add_argument('--clients',type=int,default=50)
    parser.add_argument('--rounds',type=int,default=10)
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--port',type=int,default=8101)
    parser.add_argument('--output',default='qa/completion-load-results.json')
    args=parser.parse_args()
    if not 1<=args.clients<=50 or not 1<=args.rounds<=20: parser.error('clients 1..50, rounds 1..20')
    main(args)
