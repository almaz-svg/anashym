"""Bounded report pages with totals calculated over the complete selected period."""
import csv
import io
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core import signing
from django.db.models import Q, Sum
from django.db.models.functions import TruncWeek
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import AuditEvent, LedgerEntry, Refund
from .services import ZERO, require, scoped_clients

BUSINESS_ZONE = ZoneInfo('Asia/Almaty')


def _reserved_at(client_ids, cutoff):
    """Reconstruct reserved refunds from immutable audit snapshots at the cutoff.

    Older refunds have no structured snapshots; their immutable refund ledger
    provides the completion time. Current edited fields are never used in place
    of an available historical snapshot.
    """
    refunds=list(Refund.objects.filter(client_id__in=client_ids,created_at__lte=cutoff))
    if not refunds:return {}
    ids=[str(item.pk) for item in refunds]
    snapshots={event.object_id:event.after for event in AuditEvent.objects.filter(object_type='refund',object_id__in=ids,created_at__lte=cutoff).order_by('object_id','-created_at','-id').distinct('object_id')}
    confirmed=set(LedgerEntry.objects.filter(kind='refund',created_at__lte=cutoff,reference__in=['refund:'+value for value in ids]).values_list('reference',flat=True))
    totals={}
    for item in refunds:
        saved=snapshots.get(str(item.pk))
        if saved:
            pending=saved.get('status')=='pending'; amount=Decimal(str(saved.get('amount',item.amount)))
        else:
            pending='refund:'+str(item.pk) not in confirmed and item.status!='cancelled'; amount=item.amount
        if pending:totals[item.client_id]=totals.get(item.client_id,ZERO)+amount
    return totals


def report(user,params,request=None):
    from .routes import serialize
    from .views import fail
    require(user,'admin','accountant','cashier','customer','courier')
    try:
        start=date.fromisoformat(params.get('from',timezone.localdate().isoformat()))
        end=date.fromisoformat(params.get('to',timezone.localdate().isoformat()))
        if end<start:raise ValueError()
        lower=datetime.combine(start,time.min,tzinfo=BUSINESS_ZONE)
        upper=datetime.combine(end+timedelta(days=1),time.min,tzinfo=BUSINESS_ZONE)
    except (ValueError,TypeError,OverflowError):fail('VALIDATION_ERROR','Некорректный период отчёта',fields={'from':['Проверьте начало и конец периода'],'to':['Проверьте начало и конец периода']})
    salt='report:'+str(user.pk)+str(sorted((key,value) for key,value in params.items() if key not in ['cursor','limit','cutoff']))
    cursor=None
    try:
        limit=int(params.get('limit',20))
        if not 1<=limit<=100:raise ValueError()
        if request is not None and params.get('cursor'):
            cursor=signing.loads(params['cursor'],salt=salt,max_age=86400)
        cutoff=parse_datetime(cursor['cutoff'] if cursor else params.get('cutoff','')) if cursor or params.get('cutoff') else timezone.now()
        if not cutoff or timezone.is_naive(cutoff):raise ValueError()
        if cursor and params.get('cutoff') and parse_datetime(params['cutoff'])!=cutoff:raise ValueError()
    except (ValueError,TypeError,KeyError,signing.BadSignature):fail('VALIDATION_ERROR','Некорректный cutoff или пагинация')
    clients=scoped_clients(user)
    if params.get('client_id'):clients=clients.filter(pk=params['client_id'])
    historical=LedgerEntry.objects.filter(client__in=clients,created_at__lt=upper,created_at__lte=cutoff)
    if user.role in ['cashier','courier']:historical=historical.filter(Q(actor=user)|Q(reverses_entry__actor=user))
    qs=historical.filter(created_at__gte=lower)
    sums=qs.aggregate(delivered=Sum('amount',filter=Q(kind='delivery')),payments=Sum('amount',filter=Q(kind__in=['payment','payment_reversal'])),credits=Sum('amount',filter=Q(kind='return')),refunds=Sum('amount',filter=Q(kind='refund')))
    debit=sums['delivered'] or ZERO; paid=-(sums['payments'] or ZERO); credit=-(sums['credits'] or ZERO); refunded=sums['refunds'] or ZERO
    balances={row['client_id']:row['value'] for row in historical.values('client_id').annotate(value=Sum('amount'))}
    reserves=_reserved_at(clients,min(cutoff,upper-timedelta(microseconds=1))) if user.role not in ['cashier','courier'] else {}
    for client_id,reserved in reserves.items():balances[client_id]=balances.get(client_id,ZERO)+reserved
    totals={'delivered_amount':f'{debit:.2f}','turnover_amount':f'{debit-credit:.2f}',
            'debt_amount':f'{sum((max(ZERO,value) for value in balances.values()),ZERO):.2f}',
            'advance_amount':f'{sum((max(ZERO,-value) for value in balances.values()),ZERO):.2f}',
            'reserved_refund_amount':f'{sum(reserves.values(),ZERO):.2f}','paid_amount':f'{paid:.2f}',
            'return_credit_amount':f'{credit:.2f}','refund_amount':f'{refunded:.2f}','net_amount':f'{debit-paid-credit+refunded:.2f}'}
    qs=qs.select_related('actor','client','order__client')
    def row(entry):
        value=serialize(entry)
        value.update(event_at=entry.created_at.isoformat(),business_date=timezone.localtime(entry.created_at,BUSINESS_ZONE).date().isoformat(),status='confirmed')
        return value
    if params.get('format')=='csv':
        stream=io.StringIO(); writer=csv.writer(stream)
        columns=['id','created_at','event_at','business_date','client_id','order_id','kind','amount','status']
        writer.writerow(columns)
        for entry in qs.order_by('created_at','pk').iterator(chunk_size=1000):
            values=row(entry);writer.writerow([values[key] for key in columns])
        response=HttpResponse('\ufeff'+stream.getvalue(),content_type='text/csv; charset=utf-8')
        response['Content-Disposition']='attachment; filename="report.csv"'
        return response
    grouped=[]
    if params.get('group')=='weekly':
        groups=qs.order_by().annotate(week=TruncWeek('created_at',tzinfo=BUSINESS_ZONE)).values('week').annotate(delivered=Sum('amount',filter=Q(kind='delivery')),payments=Sum('amount',filter=Q(kind__in=['payment','payment_reversal'])),credits=Sum('amount',filter=Q(kind='return')),net=Sum('amount')).order_by('week')
        grouped=[{'week_start':value['week'].date().isoformat(),'delivered_amount':f'{value["delivered"] or ZERO:.2f}','paid_amount':f'{-(value["payments"] or ZERO):.2f}','return_credit_amount':f'{-(value["credits"] or ZERO):.2f}','net_amount':f'{value["net"] or ZERO:.2f}'} for value in groups]
    next_cursor=None
    if request is None:
        items=[row(entry) for entry in qs.order_by('created_at','pk').iterator(chunk_size=1000)]
    else:
        if cursor:
            try:
                stamp=parse_datetime(cursor['created_at'])
                if not stamp or timezone.is_naive(stamp):raise ValueError()
                qs=qs.filter(Q(created_at__lt=stamp)|Q(created_at=stamp,pk__lt=cursor['id']))
            except (ValueError,KeyError,TypeError):fail('VALIDATION_ERROR','Некорректная пагинация')
        page=list(qs.order_by('-created_at','-pk')[:limit+1])
        if len(page)>limit:
            last=page[limit-1]
            next_cursor=signing.dumps({'id':str(last.pk),'created_at':last.created_at.isoformat(),'cutoff':cutoff.isoformat()},salt=salt)
        items=[row(entry) for entry in page[:limit]]
    return {'items':items,'next_cursor':next_cursor,'groups':grouped,'totals':totals,'from':start.isoformat(),'to':end.isoformat(),'cutoff':cutoff.isoformat(),'generated_at':timezone.now().isoformat()},200
