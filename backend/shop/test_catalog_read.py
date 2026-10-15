from datetime import timedelta
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from .models import Product,Batch,Quota
from .catalog_read import catalog_products


class CatalogReadTests(TestCase):
    def test_available_stock_excludes_expired_and_quota_uses_selected_day(self):
        now=timezone.now()
        day=timezone.localdate()+timedelta(days=1)
        p=Product.objects.create(name='Catalog query',price='1500')
        Batch.objects.create(product=p,quantity=10,reserved=3,manufactured_at=now-timedelta(days=1),expires_at=now+timedelta(days=1))
        Batch.objects.create(product=p,quantity=50,reserved=2,manufactured_at=now-timedelta(days=2),expires_at=now-timedelta(hours=1))
        Quota.objects.create(product=p,date=day,quantity=10,reserved=4,cutoff=now+timedelta(hours=1))
        Quota.objects.create(product=p,date=day+timedelta(days=1),quantity=100,cutoff=now+timedelta(hours=1))
        with CaptureQueriesContext(connection) as queries:
            products=list(catalog_products(day,now))
            self.assertEqual(products[0]._available_qty,7)
            self.assertEqual(products[0]._quota_qty,6)
        self.assertEqual(len(queries),1)

    def test_closed_quota_is_not_available(self):
        now=timezone.now()
        p=Product.objects.create(name='Closed quota',price='1500')
        Quota.objects.create(product=p,date=timezone.localdate(),quantity=10,cutoff=now-timedelta(seconds=1))
        result=list(catalog_products(timezone.localdate(),now))[0]
        self.assertEqual(result._available_qty,0)
        self.assertEqual(result._quota_qty,0)
