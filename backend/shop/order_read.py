"""Role-scoped order pages, including an explicit courier delivery history."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
from django.db.models import OuterRef, Subquery, Sum, Value, DecimalField, Q
from django.db.models.functions import Coalesce
from .models import LedgerEntry, PaymentAllocation
from .services import ZERO, available_order_prepayments, scoped_orders


def order_page(user,request,serializer):
    from .routes import page_queryset
    from .views import fail
    params=request.GET
    history=params.get('history','active')
    if history not in ['active','delivered','all']:
        fail('VALIDATION_ERROR','Выберите активные заказы или историю')
    payments=PaymentAllocation.objects.filter(order_id=OuterRef('pk'),payment__status='confirmed').values('order_id').annotate(total=Sum('amount')).values('total')
    credits=LedgerEntry.objects.filter(order_id=OuterRef('pk'),kind='return').values('order_id').annotate(total=Sum('amount')).values('total')
    qs=scoped_orders(user).select_related('client','courier').prefetch_related('items').annotate(
        _paid_amount=Coalesce(Subquery(payments),Value(ZERO),output_field=DecimalField(max_digits=18,decimal_places=2)),
        _credit_amount=Coalesce(Subquery(credits),Value(ZERO),output_field=DecimalField(max_digits=18,decimal_places=2)),
        _payment_due_at=Subquery(LedgerEntry.objects.filter(order_id=OuterRef('pk'),kind='delivery').order_by('created_at','pk').values('period__end_exclusive')[:1]))
    if user.role=='courier':
        if history=='delivered':qs=qs.filter(status='delivered')
        elif history=='active':qs=qs.filter(Q(status__in=['ready','out_for_delivery','delivery_failed'])|Q(cash_collection_assigned=True))
    if params.get('client_id'):qs=qs.filter(client_id=params['client_id'])
    if params.get('status'):qs=qs.filter(status=params['status'])
    if params.get('search'):
        value=params['search'].strip()[:200]
        qs=qs.filter(Q(client__name__icontains=value)|Q(id__icontains=value))
    try:
        if params.get('from'):
            qs=qs.filter(created_at__gte=datetime.combine(date.fromisoformat(params['from']),time.min,tzinfo=ZoneInfo('Asia/Almaty')))
        if params.get('to'):
            qs=qs.filter(created_at__lt=datetime.combine(date.fromisoformat(params['to'])+timedelta(days=1),time.min,tzinfo=ZoneInfo('Asia/Almaty')))
    except (ValueError,OverflowError):fail('VALIDATION_ERROR','Некорректный период',fields={'from':['Проверьте дату'],'to':['Проверьте дату']})
    page,cursor=page_queryset(qs,request)
    advances={}
    for order in page:
        if not order.delivered_total:
            if order.client_id not in advances:advances[order.client_id]=available_order_prepayments(order.client_id)
            order._available_prepayment=advances[order.client_id].get(order.pk,ZERO)
    return {'items':[serializer(order) for order in page],'next_cursor':cursor},200
