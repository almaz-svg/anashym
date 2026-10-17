"""Transactional accounting primitives. Positive ledger amounts mean client debt."""
import uuid,json
from decimal import Decimal,InvalidOperation
from datetime import timedelta
from django.db.models import Sum,Min,Q,OuterRef,Subquery,Exists,Value,DecimalField,F
from django.db.models.functions import Coalesce,Greatest
from django.utils import timezone
from django.core.serializers.json import DjangoJSONEncoder
from .models import *

ZERO=Decimal('0.00')

def money(value,positive=True):
    from .views import fail
    try:
        result=Decimal(str(value))
        if not result.is_finite() or result.as_tuple().exponent < -2 or abs(result)>Decimal('9999999999999999') or (positive and result<=0): raise InvalidOperation()
        return result
    except (InvalidOperation,ValueError,TypeError): fail('VALIDATION_ERROR','Некорректная сумма')

def require(user,*roles):
    from .views import fail
    if user.role not in roles: fail('FORBIDDEN','Недостаточно прав',403)

def sanitize_audit(value):
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            normalized=str(key).lower().replace('-','_')
            if (normalized!='must_change_password' and any(secret in normalized for secret in ['password','token','secret','authorization'])) or normalized in {'phone','email','username','address','recipient','address_snapshot','file','content_hash'}:continue
            result[key]=sanitize_audit(item)
        return result
    if isinstance(value,(list,tuple)):return [sanitize_audit(item) for item in value]
    return value


def snapshot(obj):
    fields={field.attname:getattr(obj,field.attname) for field in obj._meta.concrete_fields if field.name not in {'file'}}
    return sanitize_audit(json.loads(json.dumps(fields,cls=DjangoJSONEncoder)))

def audit(user,action,obj,details=None,before=None):
    safe=sanitize_audit(details or {})
    recipients=set()
    order=obj if isinstance(obj,Order) else getattr(obj,'order',None)
    client=getattr(obj,'client',None) or (order.client if order else None)
    if client:safe['client_name']=client.name
    AuditEvent.objects.create(actor=user,action=action,object_id=str(obj.pk),object_type=obj._meta.model_name,details=safe,before=sanitize_audit(before if before is not None else getattr(obj,'_audit_before',{})),after=snapshot(obj),reason=str(safe.get('reason','')))
    if client:recipients.update(User.objects.filter(client=client).values_list('pk',flat=True))
    if order and order.courier_id:recipients.add(order.courier_id)
    if action.endswith(('requested','created','invited')):recipients.update(User.objects.filter(role='admin').values_list('pk',flat=True))
    Notification.objects.bulk_create([Notification(user_id=recipient,message=action,object_id=str(obj.pk)) for recipient in recipients])

def scoped_orders(user):
    qs=Order.objects.all()
    if user.role=='customer': qs=qs.filter(client_id=user.client_id)
    elif user.role=='courier': qs=qs.filter(courier=user)
    return qs

def overdue_amount(client):
    payments=PaymentAllocation.objects.filter(order_id=OuterRef('pk'),payment__status='confirmed').values('order_id').annotate(total=Sum('amount')).values('total')
    credits=LedgerEntry.objects.filter(order_id=OuterRef('pk'),kind='return').values('order_id').annotate(total=Sum('amount')).values('total')
    due=LedgerEntry.objects.filter(order_id=OuterRef('pk'),kind='delivery',period__end_exclusive__lte=timezone.localdate())
    decimal=DecimalField(max_digits=18,decimal_places=2)
    orders=Order.objects.filter(client=client,delivered_total__gt=0).annotate(is_due=Exists(due),paid=Coalesce(Subquery(payments),Value(ZERO),output_field=decimal),credits=Coalesce(Subquery(credits),Value(ZERO),output_field=decimal)).filter(is_due=True)
    return orders.aggregate(total=Sum(Greatest(F('delivered_total')+F('credits')-F('paid'),Value(ZERO),output_field=decimal)))['total'] or ZERO

def scoped_clients(user):
    if user.role=='customer': return Client.objects.filter(pk=user.client_id)
    if user.role=='courier': return Client.objects.filter(order__courier=user).distinct()
    return Client.objects.all()

def get_order(user,pk,lock=False):
    from .views import fail
    try:
        qs=scoped_orders(user)
        if lock: qs=qs.select_for_update()
        order=qs.get(pk=pk)
        if lock:order._audit_before=snapshot(order)
        return order
    except (Order.DoesNotExist,ValueError): fail('NOT_FOUND','Заказ не найден',404)

def apply_due_period_change(client,day=None):
    day=day or timezone.localdate()
    if client.pending_period_days and client.period_change_at and client.period_change_at<=day:
        client.period_days=client.pending_period_days; client.period_start=client.period_change_at; client.pending_period_days=None; client.period_change_at=None
        client.save(update_fields=['period_days','period_start','pending_period_days','period_change_at'])
    return client

def post_ledger(user,client,amount,kind,order=None,reference=None,reverses_entry=None,reason=''):
    client=Client.objects.select_for_update().get(pk=client.pk)
    apply_due_period_change(client)
    day=timezone.localdate(); start=client.period_start+timedelta(days=max(0,(day-client.period_start).days//client.period_days)*client.period_days)
    period,_=Period.objects.get_or_create(client=client,start=start,defaults={'end_exclusive':start+timedelta(days=client.period_days)})
    entry=LedgerEntry.objects.create(client=client,order=order,amount=amount,kind=kind,actor=user,reference=reference or str(uuid.uuid4()),period=period,reverses_entry=reverses_entry,reason=reason)
    client.balance+=amount; client.save(update_fields=['balance'])
    audit(user,'ledger.'+kind,entry,{'amount':str(amount),'client_id':str(client.pk),'reason':reason})
    return entry

def cash_balance(courier):
    return CashMovement.objects.filter(courier=courier).aggregate(total=Sum('amount'))['total'] or ZERO

def cash_available(courier):
    reserved=Handover.objects.filter(courier=courier,status='pending').aggregate(total=Sum('amount'))['total'] or ZERO
    return cash_balance(courier)-reserved

def payment_data(p):
    allocations=list(p.allocations.all())
    available=p._available_advance if hasattr(p,'_available_advance') else available_payment_advances(p.client_id).get(p.pk,ZERO)
    return {'client_name':p.client.name,'actor_name':p.actor.get_full_name() or p.actor.username,'id':str(p.pk),'client_id':str(p.client_id),'order_id':str(p.order_id) if p.order_id else None,'method':p.method,'amount':f'{p.amount:.2f}','amount_amount':f'{p.amount:.2f}','status':p.status,'state':'pending_review' if p.status=='pending' else p.status,'reference':p.reference,'created_at':p.created_at.isoformat(),'confirmed_at':p.confirmed_at.isoformat() if p.confirmed_at else None,'actor_id':str(p.actor_id),'confirmed_by':str(p.confirmed_by_id) if p.confirmed_by_id else None,'proof_id':str(p.proof_id) if p.proof_id else None,'reversed_at':p.reversed_at.isoformat() if p.reversed_at else None,'reversed_by':str(p.reversed_by_id) if p.reversed_by_id else None,'reversal_reason':p.reversal_reason,'unallocated_amount':f'{available:.2f}','cash_holder_kind':p.cash_holder_kind,'cash_holder_id':str(p.actor_id) if p.method=='cash' and p.cash_holder_kind=='courier' else None,'allocations':[{'order_id':str(a.order_id),'amount':f'{a.amount:.2f}'} for a in allocations]}

def financial_amounts(client):
    reserved=Refund.objects.filter(client=client,status='pending').aggregate(total=Sum('amount'))['total'] or ZERO
    usable_balance=client.balance+reserved
    return {'balance':client.balance,'reserved_refund':reserved,'debt':max(ZERO,usable_balance),'advance':max(ZERO,-usable_balance)}


def unallocated_payment_funds(client_id,reserve_pending=True):
    statuses=['confirmed','pending'] if reserve_pending else ['confirmed']
    refunded={row['order_id']:row['total'] for row in Refund.objects.filter(client_id=client_id,status__in=statuses).values('order_id').annotate(total=Sum('amount'))}
    general=refunded.pop(None,ZERO)
    payments=Payment.objects.filter(client_id=client_id,status='confirmed').annotate(allocated=Coalesce(Sum('allocations__amount'),Value(ZERO),output_field=DecimalField(max_digits=18,decimal_places=2))).order_by('confirmed_at','id')
    result=[]
    for payment in payments:
        free=max(ZERO,payment.amount-payment.allocated)
        specific=min(refunded.get(payment.order_id,ZERO),free)
        if specific:refunded[payment.order_id]-=specific;free-=specific
        returned=min(general,free);general-=returned;free-=returned
        result.append((payment,free))
    return result


def available_advances(client_id):
    client=Client.objects.get(pk=client_id)
    advance=financial_amounts(client)['advance']
    if not advance:return {},{}
    by_payment={};by_order={}
    for payment,free in unallocated_payment_funds(client_id):
        available=min(advance,free);advance-=available
        if available:by_payment[payment.pk]=available
        if payment.order_id and available:by_order[payment.order_id]=by_order.get(payment.order_id,ZERO)+available
        if not advance:break
    return by_payment,by_order

def available_payment_advances(client_id):
    return available_advances(client_id)[0]

def available_order_prepayments(client_id):
    return available_advances(client_id)[1]

def available_order_prepayment(order):
    return available_order_prepayments(order.client_id).get(order.pk,ZERO)

def confirm_payment(user,p,reason=''):
    from .views import fail
    if p.status!='pending': fail('INVALID_STATE','Платёж уже обработан',409)
    if p.method=='kaspi' and user.role=='admin' and (not isinstance(reason,str) or not reason.strip()):fail('VALIDATION_ERROR','Администратор указывает основание подтверждения Kaspi')
    before=snapshot(p)
    if p.method=='kaspi' and not p.reference: fail('VALIDATION_ERROR','Нужен уникальный номер внешней операции')
    post_ledger(user,p.client,-p.amount,'payment',p.order,reference='payment:'+str(p.pk))
    remaining=p.amount
    orders=Order.objects.filter(client=p.client,delivered_total__gt=0).annotate(first_delivery=Min('ledgerentry__created_at',filter=Q(ledgerentry__kind='delivery'))).order_by('first_delivery','id')
    if p.order_id: orders=orders.filter(pk=p.order_id)
    for order in orders:
        allocated=PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or ZERO
        credit=LedgerEntry.objects.filter(order=order,kind='return').aggregate(total=Sum('amount'))['total'] or ZERO
        due=max(ZERO,order.delivered_total+credit-allocated)
        take=min(due,remaining)
        if take: PaymentAllocation.objects.create(payment=p,order=order,amount=take); remaining-=take
        if not remaining: break
    if p.method=='cash':
        p.cash_holder_kind='courier' if p.actor.role=='courier' else 'cashbox'
        if p.cash_holder_kind=='courier':CashMovement.objects.create(courier=p.actor,actor=user,amount=p.amount,kind='collection')
        else:CashboxMovement.objects.create(cashier=p.actor,amount=p.amount,kind='collection')
    p.status='confirmed'; p.confirmed_at=timezone.now(); p.confirmed_by=user; p.save(update_fields=['status','confirmed_at','confirmed_by','cash_holder_kind']); audit(user,'payment.confirmed',p,{'reason':reason},before=before)
    if p.order_id and p.order.status in ['cancelled','expired']:ensure_cancellation_refund(user,p.order,'Оплата отменённого заказа')
    return p

def reverse_payment(user,p,reason):
    from .views import fail
    require(user,'admin','accountant')
    if not isinstance(reason,str) or not reason.strip():fail('VALIDATION_ERROR','Укажите основание сторно')
    if p.status!='confirmed':fail('INVALID_STATE','Сторно возможно только для подтверждённого платежа',409)
    client=Client.objects.select_for_update().get(pk=p.client_id)
    original=LedgerEntry.objects.get(reference='payment:'+str(p.pk),kind='payment')
    before=snapshot(p)
    if p.method=='cash':
        holder=User.objects.select_for_update().get(pk=p.actor_id)
        if p.cash_holder_kind not in ['courier','cashbox']:fail('CASH_CUSTODY_UNKNOWN','Для старого платежа не сохранено место хранения наличных. Требуется сверка кассы',409)
        if p.cash_holder_kind=='courier':
            if cash_available(holder)<p.amount:fail('CASH_UNAVAILABLE','Наличные уже сданы или зарезервированы. Сначала согласуйте исправление кассовой передачи',409)
            CashMovement.objects.create(courier=holder,actor=user,amount=-p.amount,kind='payment_reversal')
        else:CashboxMovement.objects.create(cashier=holder,amount=-p.amount,kind='payment_reversal')
    post_ledger(user,client,p.amount,'payment_reversal',p.order,reference='payment-reversal:'+str(p.pk),reverses_entry=original,reason=reason.strip())
    p.allocations.all().delete()
    p.status='reversed'; p.reversed_at=timezone.now(); p.reversed_by=user; p.reversal_reason=reason.strip(); p.save(update_fields=['status','reversed_at','reversed_by','reversal_reason'])
    reconcile_pending_refunds(user,client,reason)
    allocate_advance(client)
    audit(user,'payment.reversed',p,{'reason':reason.strip(),'ledger_entry_id':str(original.pk)},before=before)
    return p

def reconcile_pending_refunds(user,client,reason):
    funds=[(payment,free) for payment,free in unallocated_payment_funds(client.pk,False)]
    pending=list(Refund.objects.select_for_update().filter(client=client,status='pending').order_by('created_at','id'))
    pending.sort(key=lambda refund:refund.order_id is None)
    for refund in pending:
        available=sum((free for payment,free in funds if not refund.order_id or payment.order_id==refund.order_id),ZERO)
        amount=min(refund.amount,available)
        if amount!=refund.amount:
            before=snapshot(refund);refund.amount=amount
            if not amount:refund.status='cancelled'
            refund.save();audit(user,'refund.revised',refund,{'reason':reason},before=before)
        left=amount;remaining=[]
        for payment,free in funds:
            take=min(left,free) if not refund.order_id or payment.order_id==refund.order_id else ZERO
            left-=take;remaining.append((payment,free-take))
        funds=remaining


def ensure_cancellation_refund(user,order,reason='Отмена оплаченного заказа'):
    """Create one obligation from money still available; no money moves here."""
    client=Client.objects.select_for_update().get(pk=order.client_id)
    reference='cancelled-order:'+str(order.pk)
    previous=Refund.objects.filter(order=order,source_reference__startswith=reference)
    existing=previous.filter(status='pending').first()
    pending=Refund.objects.filter(client=client,status='pending').aggregate(total=Sum('amount'))['total'] or ZERO
    amount=min(available_order_prepayment(order),max(ZERO,-client.balance-pending))
    if amount<=0:return existing
    if existing:
        before=snapshot(existing)
        existing.amount+=amount;existing.save(update_fields=['amount'])
        audit(user,'refund.revised',existing,{'reason':reason,'automatic':True},before=before)
        return existing
    if previous.exists():reference+=':followup:'+str(previous.count()+1)
    obj=Refund.objects.create(client=client,order=order,source_reference=reference,amount=amount,method=order.payment_mode if order.payment_mode in ['cash','kaspi'] else 'kaspi',reason=reason)
    audit(user,'refund.created',obj,{'reason':reason,'automatic':True})
    return obj

def release_reservations(order,consume=False):
    reserved_value=ZERO
    for r in Reservation.objects.select_for_update().filter(order=order):
        product_id=r.batch.product_id if r.batch_id else r.quota.product_id
        item=order.items.get(product_id=product_id); reserved_value+=item.unit_price*r.quantity
        source=r.batch or r.quota
        source=type(source).objects.select_for_update().get(pk=source.pk)
        if not r.in_transit:
            source.reserved-=r.quantity
            if consume and r.batch_id: source.quantity-=r.quantity
            source.save()
        r.delete()
    c=Client.objects.select_for_update().get(pk=order.client_id)
    if order.payment_mode=='deferred': c.reserved_credit=max(ZERO,c.reserved_credit-reserved_value); c.save(update_fields=['reserved_credit'])

def credit_return(user,obj):
    if obj.credited: return
    for row in obj.items:
        item=OrderItem.objects.select_for_update().get(order=obj.order,product_id=row['product_id'])
        from .views import fail
        if item.returned_quantity+row['quantity']>item.delivered_quantity: fail('RETURN_EXCEEDS_DELIVERED','Превышен остаток возврата',409)
        item.returned_quantity+=row['quantity']; item.save()
        if obj.received and not StockMovement.objects.filter(return_request=obj,product=item.product).exists(): StockMovement.objects.create(product=item.product,return_request=obj,quantity=row['quantity'],disposition=obj.disposition,reason=obj.reason,actor=user)
    post_ledger(user,obj.order.client,-obj.amount,'return',obj.order,reference='return:'+str(obj.pk)); obj.credited=True; obj.save()
    allocated=PaymentAllocation.objects.filter(order=obj.order).aggregate(total=Sum('amount'))['total'] or ZERO
    credits=-(LedgerEntry.objects.filter(order=obj.order,kind='return').aggregate(total=Sum('amount'))['total'] or ZERO)
    excess=max(ZERO,allocated-max(ZERO,obj.order.delivered_total-credits))
    for allocation in PaymentAllocation.objects.select_for_update().filter(order=obj.order).order_by('-payment__confirmed_at','-id'):
        take=min(excess,allocation.amount); allocation.amount-=take; excess-=take
        if allocation.amount:allocation.save()
        else:allocation.delete()
        if not excess:break
    allocate_advance(obj.order.client)

def allocate_advance(client):
    client=Client.objects.select_for_update().get(pk=client.pk)
    outstanding=ZERO
    for order in Order.objects.filter(client=client,delivered_total__gt=0):
        allocated=PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or ZERO
        credits=LedgerEntry.objects.filter(order=order,kind='return').aggregate(total=Sum('amount'))['total'] or ZERO
        outstanding+=max(ZERO,order.delivered_total+credits-allocated)
    reserved=financial_amounts(client)['reserved_refund']
    budget=min(outstanding,max(ZERO,outstanding-client.balance-reserved))
    for payment,available in unallocated_payment_funds(client.pk):
        free=min(budget,available)
        if free<=0:continue
        for order in Order.objects.filter(client=client,delivered_total__gt=0).annotate(first_delivery=Min('ledgerentry__created_at',filter=Q(ledgerentry__kind='delivery'))).order_by('first_delivery','id'):
            allocated=PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or ZERO
            credits=LedgerEntry.objects.filter(order=order,kind='return').aggregate(total=Sum('amount'))['total'] or ZERO
            take=min(free,max(ZERO,order.delivered_total+credits-allocated))
            if take:PaymentAllocation.objects.create(payment=payment,order=order,amount=take); free-=take; budget-=take
            if not free:break

def period_rows(client):
    entries=list(LedgerEntry.objects.filter(client=client).order_by('created_at'))
    buckets={}
    for entry in entries:
        day=timezone.localtime(entry.created_at).date()
        offset=max(0,(day-client.period_start).days//client.period_days)
        start=entry.period.start if entry.period_id else client.period_start+timedelta(days=offset*client.period_days)
        end=entry.period.end_exclusive if entry.period_id else start+timedelta(days=client.period_days)
        row=buckets.setdefault(start,{'period_start':start.isoformat(),'period_end_exclusive':end.isoformat(),'charged_amount':ZERO,'paid_amount':ZERO,'credit_amount':ZERO,'balance_amount':ZERO})
        row['balance_amount']+=entry.amount
        if entry.kind=='delivery': row['charged_amount']+=entry.amount
        elif entry.kind in ['payment','payment_reversal']: row['paid_amount']-=entry.amount
        elif entry.kind=='return': row['credit_amount']-=entry.amount
    for row in buckets.values(): row['current_outstanding_amount']=ZERO
    for order in Order.objects.filter(client=client,delivered_total__gt=0):
        first=LedgerEntry.objects.filter(order=order,kind='delivery').order_by('created_at').first()
        if not first:continue
        day=timezone.localtime(first.created_at).date(); offset=max(0,(day-client.period_start).days//client.period_days); start=first.period.start if first.period_id else client.period_start+timedelta(days=offset*client.period_days)
        paid=PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or ZERO
        credit=LedgerEntry.objects.filter(order=order,kind='return').aggregate(total=Sum('amount'))['total'] or ZERO
        if start in buckets:buckets[start]['current_outstanding_amount']+=max(ZERO,order.delivered_total+credit-paid)
    return [{**r,**{k:f'{v:.2f}' for k,v in r.items() if isinstance(v,Decimal)}} for _,r in sorted(buckets.items())]
