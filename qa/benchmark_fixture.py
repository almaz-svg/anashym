"""Create 100k orders / 500k lines in an isolated restored verification database.

Refuses the application database. Run migrations on the verification database
first, then pass --confirm-isolated. This is synthetic capacity data, not sales.
"""
import argparse
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')


def main(args):
    database=os.environ.get('DB_NAME','')
    if not args.confirm_isolated or not database.startswith('verify_'):
        raise SystemExit('Refusing: requires DB_NAME=verify_<id> and --confirm-isolated')
    import django
    django.setup()
    from django.utils import timezone
    from django.db import transaction
    from shop.models import Client,User,DeliveryPoint,Product,Order,OrderItem,LedgerEntry
    started=time.monotonic()
    if Client.objects.filter(name='Capacity benchmark synthetic').exists():
        raise SystemExit('Fixture already exists: refusing duplicate generation')
    client=Client.objects.create(name='Capacity benchmark synthetic',approval_status='active',deferred_approved=True,
        credit_limit=Decimal('1000000000.00'),period_start=timezone.localdate())
    user=User.objects.create_user(username='+77019999999',password='CapacityLocalOnly2026!',client=client)
    point=DeliveryPoint.objects.create(client=client,address='Synthetic benchmark only',recipient='Benchmark',phone=user.username)
    products=[Product.objects.create(name=f'Synthetic capacity product {i}',price='1500.00',active=False) for i in range(5)]
    now=timezone.now()-timedelta(days=1)
    for offset in range(0,args.orders,1000):
        count=min(1000,args.orders-offset)
        with transaction.atomic():
            orders=Order.objects.bulk_create([Order(client=client,delivery_point=point,address_snapshot=json.dumps({'address':'Synthetic benchmark only','recipient':'Benchmark','phone':user.username}),
                kind='regular',payment_mode='deferred',status='delivered',total='7500.00',delivered_total='7500.00',requested_delivery_at=now)
                for _ in range(count)])
            OrderItem.objects.bulk_create([OrderItem(order=order,product=product,name=product.name,quantity=1,
                delivered_quantity=1,unit_price='1500.00') for order in orders for product in products],batch_size=1000)
            LedgerEntry.objects.bulk_create([LedgerEntry(client=client,order=order,kind='delivery',amount='7500.00',actor=user,
                reference='benchmark:'+str(order.pk)) for order in orders],batch_size=1000)
    Client.objects.filter(pk=client.pk).update(balance=Decimal('7500.00')*args.orders)
    result={'database':database,'synthetic':True,'orders_added':args.orders,'items_added':args.orders*5,
        'total_orders':Order.objects.count(),'total_items':OrderItem.objects.count(),'seconds':round(time.monotonic()-started,3),
        'customer_phone':user.username,'customer_password':'CapacityLocalOnly2026!'}
    (ROOT/'qa/benchmark-fixture-results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='customer_password'}))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--orders',type=int,default=100000)
    parser.add_argument('--confirm-isolated',action='store_true')
    args=parser.parse_args()
    if not 1<=args.orders<=100000: parser.error('orders must be 1..100000')
    main(args)
