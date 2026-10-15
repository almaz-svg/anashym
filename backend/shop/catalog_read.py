"""One read query for product stock and date-specific production availability."""
from django.db.models import Sum,F,OuterRef,Subquery,Value,IntegerField
from django.db.models.functions import Coalesce
from django.utils import timezone
from .models import Product,Batch,Quota


def catalog_products(day,now=None):
    now=now or timezone.now()
    batches=Batch.objects.filter(product_id=OuterRef('pk'),manufactured_at__lte=now,expires_at__gt=now).values('product_id').annotate(total=Sum(F('quantity')-F('reserved'))).values('total')
    quotas=Quota.objects.filter(product_id=OuterRef('pk'),date=day,cutoff__gt=now).values('product_id').annotate(total=Sum(F('quantity')-F('reserved'))).values('total')
    return Product.objects.filter(active=True).annotate(
        _available_qty=Coalesce(Subquery(batches),Value(0),output_field=IntegerField()),
        _quota_qty=Coalesce(Subquery(quotas),Value(0),output_field=IntegerField()),
    ).order_by('name','id')
