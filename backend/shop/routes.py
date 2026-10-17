"""Role-scoped MVP routes; mutations run inside the common atomic dispatcher."""
import csv,io,uuid
from django.core import signing
from django.contrib.sessions.models import Session
from datetime import date,timedelta
from django.http import HttpResponse
from django.db.models import Sum
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import *
from .services import *
from .workflow import transition,fulfill,deliver,version_check

def serialize(obj):
    result={}
    for field in obj._meta.concrete_fields:
        value=getattr(obj,field.attname)
        if isinstance(value,(Decimal,uuid.UUID)): value=str(value)
        elif hasattr(value,'isoformat'): value=value.isoformat()
        elif hasattr(value,'url'): value=str(value)
        result[field.attname]=value
    fields={field.name for field in obj._meta.concrete_fields}
    for name in ['actor','courier','cashier']:
        if name in fields:
            person=getattr(obj,name,None)
            result[name+'_name']=(person.get_full_name() or person.username) if person else None
    if 'client' in fields:result['client_name']=obj.client.name
    elif 'order' in fields and obj.order_id:result['client_name']=obj.order.client.name
    if 'product' in fields:result['product_name']=obj.product.name
    if isinstance(obj,AuditEvent):
        result['client_name']=obj.details.get('client_name')
        result['object_name']=obj.after.get('name') or obj.details.get('object_name') or result['client_name']
    return result

def page_queryset(qs,request):
    """Signed keyset pages remain reachable as new events are appended."""
    from .views import fail
    has_time=any(f.name=='created_at' for f in qs.model._meta.concrete_fields)
    salt=request.path+str(sorted((k,v) for k,v in request.GET.items() if k not in ['cursor','limit']))
    try:
        limit=int(request.GET.get('limit',20))
        if not 1<=limit<=100:raise ValueError()
        if request.GET.get('cursor'):
            cursor=signing.loads(request.GET['cursor'],salt=salt,max_age=86400)
            if has_time:
                stamp=parse_datetime(cursor['created_at'])
                if not stamp or timezone.is_naive(stamp):raise ValueError()
                qs=qs.filter(Q(created_at__lt=stamp)|Q(created_at=stamp,pk__lt=cursor['id']))
            else:qs=qs.filter(pk__lt=cursor['id'])
    except (ValueError,KeyError,TypeError,signing.BadSignature):fail('VALIDATION_ERROR','Некорректная пагинация')
    page=list(qs.order_by('-created_at','-pk')[:limit+1] if has_time else qs.order_by('-pk')[:limit+1])
    cursor=None
    if len(page)>limit:
        last=page[limit-1]; value={'id':str(last.pk)}
        if has_time:value['created_at']=last.created_at.isoformat()
        cursor=signing.dumps(value,salt=salt)
    return page[:limit],cursor

def rows(qs,request,serializer=serialize):
    fields={field.name for field in qs.model._meta.concrete_fields}
    relations=[name for name in ['actor','courier','cashier','client','product'] if name in fields]
    if 'order' in fields:relations.append('order__client')
    if relations:qs=qs.select_related(*relations)
    page,cursor=page_queryset(qs,request)
    return {'items':[serializer(o) for o in page],'next_cursor':cursor}

def client_data(client):
    payload=serialize(client); due=overdue_amount(client); amounts=financial_amounts(client)
    payload.update(overdue=f'{due:.2f}',overdue_amount=f'{due:.2f}',balance_amount=f'{client.balance:.2f}',debt_amount=f'{amounts["debt"]:.2f}',advance_amount=f'{amounts["advance"]:.2f}',reserved_refund_amount=f'{amounts["reserved_refund"]:.2f}')
    return payload

def locked_payment(pk,reverse=False):
    """Match delivery's custody -> client -> payment lock order."""
    from .views import fail
    try:payment=Payment.objects.get(pk=pk)
    except Payment.DoesNotExist:fail('NOT_FOUND','Платёж не найден',404)
    if reverse and payment.method=='cash':User.objects.select_for_update().get(pk=payment.actor_id)
    Client.objects.select_for_update().get(pk=payment.client_id)
    return Payment.objects.select_for_update().get(pk=pk)

def client_for(user,data):
    from .views import fail
    if user.role=='customer': return user.client
    try: return Client.objects.get(pk=data.get('client_id'))
    except (Client.DoesNotExist,ValueError): fail('VALIDATION_ERROR','Укажите клиента')

from .reporting import report


def handle(request,route,data):
    from .views import fail,order_data,order_detail,listing,available,place_order
    user=request.user; method=request.method; parts=route.split('/')
    from .access_management import handle_access
    from .catalog_details import handle_catalog
    for handler in [handle_access,handle_catalog]:
        handled=handler(request,route,data)
        if handled is not None:return handled
    def visible_order(order,detail=False):
        payload=order_detail(order,user) if detail else order_data(order)
        if user.role in ['cashier','accountant']:payload['address_snapshot']={}
        return payload
    if route=='profile' and method=='GET':
        from .customer_profile import customer_profile
        return customer_profile(user,request.GET)
    if route.startswith('files'):
        from .photos import handle as photo_handle
        return photo_handle(request,route,data)
    if route=='orders' and method=='POST' and user.role=='admin':
        ai_used=data.get('ai_used',False)
        if type(ai_used) is not bool: fail('VALIDATION_ERROR','ai_used должен быть логическим значением')
        client=client_for(user,data); body={k:v for k,v in data.items() if k not in {'client_id','ai_used'}}
        result,status=place_order(user,body,client=client,ai_used=ai_used)
        audit(user,'order.admin_created',Order.objects.get(pk=result['id']),{'client_id':str(client.pk),'ai_used':ai_used})
        return result,status
    if route=='delivery-points':
        require(user,'admin','customer'); qs=DeliveryPoint.objects.all() if user.role=='admin' else DeliveryPoint.objects.filter(client=user.client)
        if request.GET.get('client_id'): qs=qs.filter(client_id=request.GET['client_id'])
        if method=='GET':return rows(qs,request),200
        client=client_for(user,data)
        import re
        if not isinstance(data.get('address'),str) or not data['address'].strip() or len(data['address'])>300 or not str(data.get('recipient','')).strip() or not re.fullmatch(r'\+[1-9]\d{7,14}',str(data.get('phone',''))):fail('VALIDATION_ERROR','Проверьте адрес, получателя и телефон')
        obj=DeliveryPoint.objects.create(client=client,address=data['address'],recipient=data['recipient'][:150],phone=data['phone'],window_start=data.get('window_start','09:00'),window_end=data.get('window_end','20:00'))
        obj.full_clean(); audit(user,'delivery_point.created',obj);return serialize(obj),201
    if route=='catalog' and method=='GET' and user.role!='customer':
        require(user,'admin','cashier','accountant'); now=timezone.now()
        try: day=date.fromisoformat(request.GET.get('delivery_date',timezone.localdate().isoformat()))
        except ValueError: fail('VALIDATION_ERROR','Некорректная дата')
        from .catalog_read import catalog_products
        from .catalog_details import catalog_rows
        return listing(request,catalog_rows(catalog_products(day,now),now)),200
    if route=='balance' and user.role!='customer':
        require(user,'admin','cashier','accountant'); clients=scoped_clients(user)
        if request.GET.get('client_id'):clients=clients.filter(pk=request.GET['client_id'])
        values=rows(clients,request,client_data)
        amounts=[financial_amounts(c) for c in clients]
        return {**values,'debt_amount':f'{sum((a["debt"] for a in amounts),ZERO):.2f}','advance_amount':f'{sum((a["advance"] for a in amounts),ZERO):.2f}','reserved_refund_amount':f'{sum((a["reserved_refund"] for a in amounts),ZERO):.2f}','overdue_amount':f'{sum((overdue_amount(c) for c in clients),ZERO):.2f}','currency':'KZT'},200
    if route=='orders' and method=='GET':
        from .order_read import order_page
        return order_page(user,request,visible_order)
    if parts[0]=='orders' and len(parts)>=2:
        order=get_order(user,parts[1],lock=method=='POST')
        if user.role=='courier' and method=='GET' and order.status not in ['ready','out_for_delivery','delivery_failed','delivered'] and not order.cash_collection_assigned: fail('NOT_FOUND','Активное назначение не найдено',404)
        if method=='GET': return visible_order(order,True),200
        action=parts[2] if len(parts)>2 else ''
        if action=='transition':
            if user.role=='customer':
                if data.get('status')!='cancelled' or order.status!='submitted': fail('FORBIDDEN','Отмена уже недоступна',403)
                version_check(order,data); release_reservations(order); order.status='cancelled'; order.version+=1; order.reservation_expires_at=None; order.save(); ensure_cancellation_refund(user,order,str(data.get('reason') or 'Отмена клиентом')); audit(user,'order.cancelled',order,data)
            else: transition(user,order,data)
        elif action=='fulfill': fulfill(user,order,data)
        elif action=='delivery': deliver(user,order,data)
        elif action=='delivery-failed':
            require(user,'courier','admin'); version_check(order,data)
            if order.status!='out_for_delivery' or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Укажите причину неудачи для активной доставки',409)
            order.status='delivery_failed'; order.version+=1; order.save(); audit(user,'order.delivery_failed',order,data)
            DeliveryAttempt.objects.create(order=order,courier=order.courier,outcome='failed',reason=data['reason'])
        elif action=='reschedule':
            require(user,'admin'); value=parse_datetime(str(data.get('requested_delivery_at','')))
            if 'version' in data:version_check(order,data)
            if value is None or timezone.is_naive(value) or value<=timezone.now() or order.status in ['delivered','cancelled','expired']: fail('VALIDATION_ERROR','Укажите будущую дату активного заказа')
            if not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Нужна причина переноса')
            order.proposed_delivery_at=value; order.version+=1; order.save(); audit(user,'order.reschedule_requested',order,data)
        elif action=='reschedule-confirm':
            require(user,'customer')
            if 'version' in data:version_check(order,data)
            if not order.proposed_delivery_at: fail('INVALID_STATE','Нет предложения переноса',409)
            if type(data.get('accept'))!=bool: fail('VALIDATION_ERROR','Укажите решение')
            if data['accept']:
                for r in Reservation.objects.select_for_update().filter(order=order,quota__isnull=False):
                    new=Quota.objects.select_for_update().filter(product=r.quota.product,date=timezone.localtime(order.proposed_delivery_at).date(),cutoff__gt=timezone.now()).first()
                    if not new or new.quantity-new.reserved<r.quantity: fail('STOCK_UNAVAILABLE','Нет квоты на новую дату',409)
                    old=Quota.objects.select_for_update().get(pk=r.quota_id); old.reserved-=r.quantity; old.save(); new.reserved+=r.quantity; new.save(); r.quota=new; r.save()
                order.requested_delivery_at=order.proposed_delivery_at
            order.proposed_delivery_at=None; order.version+=1; order.save(); audit(user,'order.rescheduled',order,data)
        elif action=='payment-mode':
            require(user,'admin'); version_check(order,data); client=Client.objects.select_for_update().get(pk=order.client_id)
            if order.status not in ['submitted','accepted','preparing','ready','out_for_delivery','delivery_failed'] or order.payment_mode=='deferred' or data.get('payment_mode')!='deferred' or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Режим оплаты нельзя изменить',409)
            if client.archived or client.approval_status!='active' or not client.deferred_approved or overdue_amount(client)>0 or client.credit_limit-financial_amounts(client)['debt']-client.reserved_credit<order.total: fail('CREDIT_LIMIT_EXCEEDED','Отсрочка недоступна',409)
            client.reserved_credit+=order.total; client.save(); order.payment_mode='deferred'; order.version+=1; order.save(); audit(user,'order.payment_mode',order,data)
        elif action=='assign-collection':
            require(user,'admin')
            if order.status!='delivered' or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Сбор долга назначается после доставки с основанием',409)
            order.courier=User.objects.get(pk=data.get('courier_id'),role='courier'); order.cash_collection_assigned=True; order.save(); audit(user,'order.collection_assigned',order,data)
        elif action=='goods-return':
            require(user,'admin')
            if order.status not in ['delivered','delivery_failed'] or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Нет товара для физической сдачи',409)
            for row in data.get('items',[]):
                qty=row.get('quantity'); reservations=list(Reservation.objects.select_for_update().filter(order=order,batch__product_id=row.get('product_id'),in_transit=True))
                if type(qty)!=int or qty<=0 or sum(r.quantity for r in reservations)<qty: fail('VALIDATION_ERROR','Сдача превышает остаток курьера')
                left=qty
                for r in reservations:
                    take=min(left,r.quantity); StockMovement.objects.create(product=r.batch.product,return_request=None,quantity=take,disposition='quarantine',reason=data['reason'],actor=user); r.quantity-=take
                    if r.quantity:r.save()
                    else:r.delete()
                    left-=take
                    if not left:break
            audit(user,'order.goods_return',order,data)
        else: return None
        return order_data(order),200
    if route=='staff':
        require(user,'admin','accountant','cashier')
        if method=='GET': return rows(User.objects.exclude(role='customer'),request,lambda u:{'id':str(u.pk),'name':u.get_full_name() or u.username,'phone':u.username,'role':u.role,'must_change_password':u.must_change_password}),200
        require(user,'admin')
        import re
        if data.get('role') not in ['admin','courier','cashier','accountant'] or not re.fullmatch(r'\+[1-9]\d{7,14}',str(data.get('phone',''))) or not str(data.get('name','')).strip(): fail('VALIDATION_ERROR','Проверьте телефон, имя и роль')
        staff=User.objects.create_user(username=data['phone'],first_name=data['name'][:150],role=data['role']); token=signing.dumps({'staff':str(staff.pk),'stamp':staff.password},salt='staff-invite')
        audit(user,'staff.invited',staff,{'role':staff.role}); return {'id':str(staff.pk),'phone':staff.username,'role':staff.role,'invitation_token':token,'expires_in':86400},201
    if route=='clients' and method=='GET':
        require(user,'admin','cashier','accountant'); return rows(Client.objects.all(),request,client_data),200
    if parts[0]=='clients' and len(parts)==3 and parts[2]=='approve' and method=='POST':
        require(user,'admin')
        try: client=Client.objects.select_for_update().get(pk=parts[1])
        except Client.DoesNotExist: fail('NOT_FOUND','Клиент не найден',404)
        client._audit_before=snapshot(client)
        client.approval_status=data.get('approval_status','active')
        if client.approval_status not in ['active','rejected','pending']: fail('VALIDATION_ERROR','Некорректный статус')
        if 'deferred_approved' in data and type(data['deferred_approved'])!=bool:fail('VALIDATION_ERROR','Разрешение отсрочки должно быть логическим значением')
        client.deferred_approved=data.get('deferred_approved',client.deferred_approved); client.credit_limit=money(data.get('credit_limit',data.get('credit_limit_amount',client.credit_limit)),False)
        desired=data.get('period_days',client.period_days)
        if desired not in [7,14,30] or client.credit_limit<0: fail('VALIDATION_ERROR','Проверьте период и лимит')
        if desired!=client.period_days and LedgerEntry.objects.filter(client=client).exists():
            day=timezone.localdate(); start=client.period_start+timedelta(days=max(0,(day-client.period_start).days//client.period_days)*client.period_days)
            client.pending_period_days=desired; client.period_change_at=start+timedelta(days=client.period_days)
        else:client.period_days=desired
        if data.get('period_start') and not LedgerEntry.objects.filter(client=client).exists():
            try:client.period_start=date.fromisoformat(data['period_start'])
            except ValueError:fail('VALIDATION_ERROR','Некорректное начало периода')
        client.save(); audit(user,'client.approved',client,data); return client_data(client),200
    if route in ['products','batches','quotas'] or (route=='catalog' and method=='POST'):
        if route=='catalog': route='products'
        models={'products':Product,'batches':Batch,'quotas':Quota}; model=models[route]
        if method=='GET':
            require(user,'admin','cashier','accountant'); return rows(model.objects.all(),request),200
        require(user,'admin')
        if route=='products':
            obj=Product.objects.create(name=str(data.get('name','')).strip(),description=data.get('description',''),price=money(data.get('price',data.get('price_amount'))),preparation_minutes=data.get('preparation_minutes',60))
            if not obj.name: fail('VALIDATION_ERROR','Название обязательно')
        elif route=='batches':
            quantity=data.get('quantity'); manufactured=parse_datetime(str(data.get('manufactured_at',''))); expires=parse_datetime(str(data.get('expires_at','')))
            if type(quantity)!=int or quantity<=0 or manufactured is None or expires is None or timezone.is_naive(manufactured) or timezone.is_naive(expires) or expires<=manufactured: fail('VALIDATION_ERROR','Проверьте количество и сроки партии')
            obj=Batch.objects.create(product_id=data['product_id'],quantity=quantity,manufactured_at=manufactured,expires_at=expires)
        else:
            quantity=data.get('quantity'); cutoff=parse_datetime(str(data.get('cutoff','')))
            if type(quantity)!=int or quantity<=0 or cutoff is None or timezone.is_naive(cutoff): fail('VALIDATION_ERROR','Проверьте квоту')
            obj=Quota.objects.create(product_id=data['product_id'],date=data['date'],cutoff=cutoff,quantity=quantity)
        audit(user,route+'.created',obj,data); return serialize(obj),201
    if route=='payments':
        if method=='GET':
            qs=Payment.objects.filter(client__in=scoped_clients(user))
            if user.role=='courier': qs=qs.filter(actor=user)
            if user.role=='cashier': qs=qs.filter(Q(method='kaspi',status='pending')|Q(confirmed_by=user)|Q(actor=user))
            if request.GET.get('client_id'):qs=qs.filter(client_id=request.GET['client_id'])
            if request.GET.get('order_id'):qs=qs.filter(order_id=request.GET['order_id'])
            payments,cursor=page_queryset(qs.select_related('actor','client').prefetch_related('allocations'),request)
            advances={}
            for payment in payments:
                if payment.client_id not in advances:
                    advances[payment.client_id]=available_payment_advances(payment.client_id)
                payment._available_advance=advances[payment.client_id].get(payment.pk,ZERO)
            return {'items':[payment_data(p) for p in payments],'next_cursor':cursor},200
        if data.get('method') not in ['kaspi','cash']: fail('VALIDATION_ERROR','Выберите Kaspi или наличные')
        client=client_for(user,data); order=get_order(user,data['order_id'],True) if data.get('order_id') else None
        if order and order.client_id!=client.pk: fail('VALIDATION_ERROR','Заказ другого клиента')
        if data['method']=='cash':
            require(user,'courier','cashier','admin')
            if user.role=='courier' and (not order or order.courier_id!=user.pk or (order.status=='delivered' and not order.cash_collection_assigned)): fail('FORBIDDEN','Сбор наличных только по явному назначению',403)
            ids=data.get('photo_ids',[])
            if not order or not 1<=len(ids)<=5 or Photo.objects.filter(order=order,pk__in=ids,uploaded_by=user,purpose='cash').count()!=len(ids): fail('PHOTO_REQUIRED','Для наличных нужно сохранённое фото подтверждения')
            amount=money(data.get('amount')); received=money(data.get('cash_received_amount',amount),False); change=money(data.get('cash_change_amount','0'),False)
            if received<0 or change<0 or received-change!=amount: fail('VALIDATION_ERROR','Получено минус сдача должно совпадать с суммой платежа')
            if user.role=='courier' and change>cash_available(user): fail('CASH_CHANGE_UNAVAILABLE','Недостаточно наличных для сдачи',409)
            locked=Client.objects.select_for_update().get(pk=client.pk)
            if amount>financial_amounts(locked)['debt'] and not data.get('advance_consent'): fail('ADVANCE_CONSENT_REQUIRED','Подтвердите зачисление переплаты в аванс')
        reference=str(data.get('reference','')).strip() or None
        if reference and Payment.objects.filter(reference=reference).exists(): fail('DUPLICATE_REFERENCE','Внешняя операция уже зарегистрирована',409)
        proof=None; proof_id=data.get('proof_id') or (data.get('photo_ids') or [None])[0]
        if data['method']=='kaspi':
            if user.role=='customer' and (not order or not proof_id):fail('PHOTO_REQUIRED','Приложите квитанцию Kaspi к заказу')
            if proof_id:
                proof=Photo.objects.filter(pk=proof_id,order=order,uploaded_by=user,purpose='payment').first()
                if not proof:fail('PHOTO_REQUIRED','Квитанция должна принадлежать этому заказу и текущему пользователю')
        p=Payment.objects.create(client=client,order=order,method=data['method'],amount=money(data.get('amount')),reference=reference,actor=user,proof=proof)
        if p.method=='cash': confirm_payment(user,p)
        if p.method=='cash' and order and order.cash_collection_assigned: order.cash_collection_assigned=False; order.save()
        audit(user,'payment.created',p,data); return payment_data(p),201
    if parts[0]=='payments' and len(parts)==3 and parts[2]=='reverse' and method=='POST':
        require(user,'admin','accountant')
        p=locked_payment(parts[1],reverse=True)
        return payment_data(reverse_payment(user,p,data.get('reason'))),200
    if parts[0]=='payments' and len(parts)==3 and parts[2]=='confirm' and method=='POST':
        require(user,'admin','cashier','accountant')
        p=locked_payment(parts[1])
        if data.get('reference'):
            if Payment.objects.filter(reference=data['reference']).exclude(pk=p.pk).exists(): fail('DUPLICATE_REFERENCE','Операция уже проведена',409)
            p.reference=data['reference']; p.save()
        return payment_data(confirm_payment(user,p,data.get('reason',''))),200
    if parts[0]=='payments' and len(parts)==3 and parts[2]=='reject':
        require(user,'admin','cashier','accountant'); p=locked_payment(parts[1]);p._audit_before=snapshot(p)
        if p.status!='pending' or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Нужна ожидающая заявка и основание',409)
        p.status='rejected'; p.save(); audit(user,'payment.rejected',p,{'reason':data['reason']}); return payment_data(p),200
    if route=='ledger' and method=='GET':
        require(user,'admin','cashier','accountant','customer'); qs=LedgerEntry.objects.filter(client__in=scoped_clients(user)).order_by('-created_at')
        if user.role=='cashier': qs=qs.filter(Q(actor=user)|Q(reverses_entry__actor=user))
        if request.GET.get('client_id'): qs=qs.filter(client_id=request.GET['client_id'])
        for name,lookup in [('from','created_at__date__gte'),('to','created_at__date__lte')]:
            if request.GET.get(name):
                try: value=date.fromisoformat(request.GET[name])
                except ValueError: fail('VALIDATION_ERROR','Некорректная дата')
                qs=qs.filter(**{lookup:value})
        return rows(qs,request),200
    if route=='periods' and method=='GET':
        require(user,'admin','accountant','customer')
        items=[]
        for c in scoped_clients(user):
            for p in period_rows(c):
                stored,_=Period.objects.get_or_create(client=c,start=p['period_start'],defaults={'end_exclusive':p['period_end_exclusive']})
                items.append({'id':stored.pk,'client_id':str(c.pk),'start':p['period_start'],'end_exclusive':p['period_end_exclusive'],'due_at':p['period_end_exclusive'],'closed_at':stored.closed_at.isoformat() if stored.closed_at else None,'snapshot':stored.snapshot,**p})
        return listing(request,items),200
    if route=='periods/close' and method=='POST':
        require(user,'admin','accountant')
        try: as_of=date.fromisoformat(data.get('as_of',timezone.localdate().isoformat()))
        except ValueError: fail('VALIDATION_ERROR','Некорректная дата закрытия')
        count=0
        for c in Client.objects.select_for_update().all():
            for p in period_rows(c):
                if date.fromisoformat(p['period_end_exclusive'])>as_of: continue
                stored,_=Period.objects.get_or_create(client=c,start=p['period_start'],defaults={'end_exclusive':p['period_end_exclusive']})
                if stored.closed_at: continue
                stored.snapshot=p; stored.closed_at=timezone.now(); stored.save(); audit(user,'period.closed',stored,p); count+=1
            if c.pending_period_days and c.period_change_at<=as_of:
                c.period_days=c.pending_period_days; c.period_start=c.period_change_at; c.pending_period_days=None; c.period_change_at=None; c.save()
        return {'closed_count':count},200
    if route in ['cash-balance','cash'] and method=='GET':
        require(user,'courier','admin','cashier','accountant')
        couriers=[user] if user.role=='courier' else User.objects.filter(role='courier')
        if request.GET.get('courier_id') and user.role!='courier': couriers=User.objects.filter(pk=request.GET['courier_id'],role='courier')
        balance=sum((cash_balance(c) for c in couriers),ZERO); available=sum((cash_available(c) for c in couriers),ZERO)
        return {'cash_amount':str(balance),'balance_amount':str(balance),'available_amount':str(available),'pending_handover_amount':str(balance-available),'reserved_amount':str(balance-available)},200
    if route=='cash-movements' and method=='GET':
        require(user,'courier','admin','cashier','accountant'); return rows(CashMovement.objects.filter(courier=user) if user.role=='courier' else CashMovement.objects.all(),request),200
    if route=='cash-movements' and method=='POST':
        require(user,'admin','cashier'); courier=User.objects.select_for_update().get(pk=data.get('courier_id'),role='courier'); amount=money(data.get('amount'))
        if not str(data.get('reason','')).strip() or data.get('direction') not in ['issue','return']: fail('VALIDATION_ERROR','Укажите направление и основание')
        if data['direction']=='return':
            if amount>cash_available(courier): fail('CASH_UNAVAILABLE','Недостаточно наличных',409)
            amount=-amount
        obj=CashMovement.objects.create(courier=courier,actor=user,amount=amount,kind=data['direction']); CashboxMovement.objects.create(cashier=user,amount=-amount,kind='float'); audit(user,'cash.float',obj,data); return serialize(obj),201
    if route=='handovers':
        require(user,'courier','admin','cashier','accountant')
        if method=='GET': return rows(Handover.objects.filter(courier=user) if user.role=='courier' else Handover.objects.all(),request),200
        require(user,'courier'); User.objects.select_for_update().get(pk=user.pk); amount=money(data.get('amount'))
        if amount>cash_available(user): fail('CASH_UNAVAILABLE','Наличные уже зарезервированы или отсутствуют',409)
        obj=Handover.objects.create(courier=user,amount=amount); audit(user,'handover.created',obj,data); return serialize(obj),201
    if parts[0]=='handovers' and len(parts)==3 and parts[2]=='confirm':
        require(user,'admin','cashier'); obj=Handover.objects.select_for_update().get(pk=parts[1]); obj._audit_before=snapshot(obj); User.objects.select_for_update().get(pk=obj.courier_id)
        if obj.status!='pending': fail('INVALID_STATE','Сдача уже подтверждена',409)
        amount=money(data.get('amount',obj.amount),False)
        if amount<0 or amount>obj.amount: fail('VALIDATION_ERROR','Принятая сумма вне заявки')
        if amount!=obj.amount and not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Укажите причину расхождения')
        obj.accepted_amount=amount; obj.status='confirmed'; obj.reason=data.get('reason',''); obj.save()
        CashMovement.objects.create(courier=obj.courier,actor=user,amount=-amount,kind='handover'); CashboxMovement.objects.create(cashier=user,amount=amount,kind='handover'); audit(user,'handover.confirmed',obj,data); return serialize(obj),200
    if parts[0]=='handovers' and len(parts)==3 and parts[2]=='reject':
        require(user,'admin','cashier'); obj=Handover.objects.select_for_update().get(pk=parts[1]);obj._audit_before=snapshot(obj)
        if obj.status!='pending' or not str(data.get('reason','')).strip(): fail('INVALID_STATE','Нужна ожидающая сдача и основание',409)
        obj.status='rejected'; obj.reason=data['reason']; obj.save(); audit(user,'handover.rejected',obj,data); return serialize(obj),200
    if route=='shifts':
        require(user,'admin','cashier','accountant')
        if method=='GET': return rows(Shift.objects.filter(cashier=user) if user.role=='cashier' else Shift.objects.all(),request),200
        require(user,'admin','cashier'); User.objects.select_for_update().get(pk=user.pk)
        current=Shift.objects.select_for_update().filter(cashier=user,closed_at__isnull=True).first()
        if current:current._audit_before=snapshot(current)
        if data.get('action')=='open':
            if current: fail('INVALID_STATE','Смена уже открыта',409)
            opening=money(data.get('opening_amount','0'),False)
            if opening<0:fail('VALIDATION_ERROR','Отрицательный остаток')
            current=Shift.objects.create(cashier=user,opening_amount=opening)
        elif data.get('action')=='close':
            if not current: fail('INVALID_STATE','Смена не открыта',409)
            expected=current.opening_amount+(CashboxMovement.objects.filter(cashier=user,created_at__gte=current.opened_at).aggregate(total=Sum('amount'))['total'] or ZERO)
            counted=money(data.get('counted_amount',data.get('actual_amount')),False)
            if counted<0: fail('VALIDATION_ERROR','Отрицательный пересчёт')
            if counted!=expected and not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Укажите причину расхождения')
            current.expected_amount=expected; current.counted_amount=counted; current.discrepancy=counted-expected; current.reason=data.get('reason',''); current.closed_at=timezone.now(); current.save()
        else: fail('VALIDATION_ERROR','Выберите open или close')
        audit(user,'shift.'+data['action'],current,data); return serialize(current),200
    if route=='returns':
        if method=='GET': return rows(ReturnRequest.objects.filter(order__in=scoped_orders(user)),request),200
        require(user,'customer','admin','courier'); order=get_order(user,data.get('order_id'),True)
        if order.delivered_total<=0: fail('INVALID_STATE','Возврат только переданного товара',409)
        entries=data.get('items',[]); seen=set(); amount=ZERO
        ids=data.get('photo_ids',[])
        if not 1<=len(ids)<=5 or Photo.objects.filter(order=order,pk__in=ids,purpose__in=['return','exchange'],uploaded_by=user).count()!=len(ids): fail('PHOTO_REQUIRED','Для возврата нужно сохранённое фото')
        if not entries or data.get('kind','return') not in ['return','exchange'] or not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Проверьте возврат')
        for row in entries:
            item=OrderItem.objects.get(order=order,product_id=row.get('product_id')); qty=row.get('quantity')
            if item.product_id in seen or type(qty)!=int or qty<=0: fail('VALIDATION_ERROR','Некорректные позиции')
            seen.add(item.product_id)
            pending=sum(r['quantity'] for ret in ReturnRequest.objects.filter(order=order,status__in=['pending','approved'],credited=False) for r in ret.items if r['product_id']==str(item.product_id))
            if qty+pending+item.returned_quantity>item.delivered_quantity: fail('RETURN_EXCEEDS_DELIVERED','Количество превышает доступное к возврату',409)
            amount+=item.unit_price*qty
        obj=ReturnRequest.objects.create(order=order,items=entries,reason=data['reason'],kind=data.get('kind','return'),amount=amount); audit(user,'return.requested',obj,data); return serialize(obj),201
    if parts[0]=='returns' and len(parts)==3:
        require(user,'admin','courier'); obj=ReturnRequest.objects.select_for_update().get(pk=parts[1]);obj._audit_before=snapshot(obj); get_order(user,obj.order_id,True)
        if obj.status=='rejected' or (obj.credited and parts[2]!='receive'): fail('INVALID_STATE','Возврат уже обработан',409)
        if parts[2]=='receive':
            ids=data.get('photo_ids',[])
            if obj.received:fail('INVALID_STATE','Физический возврат уже принят',409)
            if not 1<=len(ids)<=5 or Photo.objects.filter(order=obj.order,pk__in=ids,uploaded_by=user,purpose__in=['return','exchange']).count()!=len(ids): fail('PHOTO_REQUIRED','Нужно фото физического возврата')
            obj.received=True; obj.save()
            for row in obj.items: StockMovement.objects.create(product_id=row['product_id'],return_request=obj,quantity=row['quantity'],disposition='quarantine',reason=obj.reason,actor=user)
            if obj.status=='approved' and not obj.credited: credit_return(user,obj)
            audit(user,'return.received',obj,data)
        elif parts[2]=='decide':
            require(user,'admin')
            if data.get('decision') not in ['approve','reject'] or not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Нужно решение и основание')
            if data['decision']=='approve':
                if data.get('disposition','quarantine') not in ['quarantine','write_off']: fail('VALIDATION_ERROR','Выберите карантин или списание')
                obj.disposition=data.get('disposition','quarantine')
                if obj.received or data.get('without_collection'): credit_return(user,obj)
            obj.status='approved' if data['decision']=='approve' else 'rejected'; obj.save(); audit(user,'return.'+obj.status,obj,data)
        else: return None
        return serialize(obj),200
    if route=='refunds':
        if method=='GET' and user.role=='customer':return rows(Refund.objects.filter(client_id=user.client_id),request),200
        require(user,'admin','cashier','accountant')
        if method=='GET': return rows(Refund.objects.all(),request),200
        require(user,'admin','accountant','cashier'); client=client_for(user,data); Client.objects.select_for_update().get(pk=client.pk); amount=money(data.get('amount'))
        pending=Refund.objects.filter(client=client,status='pending').aggregate(total=Sum('amount'))['total'] or ZERO
        client.refresh_from_db()
        if amount+pending>max(ZERO,-client.balance): fail('ADVANCE_UNAVAILABLE','Возврат денег возможен только из свободного аванса',409)
        if data.get('method') not in ['cash','kaspi'] or not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Укажите способ и основание')
        obj=Refund.objects.create(client=client,amount=amount,method=data['method'],reason=data['reason']); audit(user,'refund.created',obj,data); return serialize(obj),201
    if parts[0]=='refunds' and len(parts)==3 and parts[2]=='confirm':
        require(user,'admin','cashier','accountant'); obj=Refund.objects.get(pk=parts[1]); client=Client.objects.select_for_update().get(pk=obj.client_id);obj=Refund.objects.select_for_update().get(pk=obj.pk)
        if obj.status!='pending': fail('INVALID_STATE','Возврат денег уже обработан',409)
        funds=unallocated_payment_funds(client.pk,False)
        total=sum((amount for payment,amount in funds),ZERO)
        pending=financial_amounts(client)['reserved_refund']
        matching=sum((amount for payment,amount in funds if not obj.order_id or payment.order_id==obj.order_id),ZERO)
        if pending>total or obj.amount>matching: fail('ADVANCE_UNAVAILABLE','Зарезервированные средства недоступны после исправлений',409)
        obj._audit_before=snapshot(obj)
        post_ledger(user,client,obj.amount,'refund',order=obj.order,reference='refund:'+str(obj.pk),reason=obj.reason)
        if obj.method=='cash': CashboxMovement.objects.create(cashier=user,amount=-obj.amount,kind='refund')
        obj.status='confirmed'; obj.save(); audit(user,'refund.confirmed',obj,data); return serialize(obj),200
    if route=='reports' and method=='GET':
        return report(user,request.GET,request=request)
    if route in ['weekly-reports','reports/weekly'] and method=='GET':
        require(user,'admin','accountant','customer'); result=[]
        report_page,cursor=page_queryset(WeeklyReport.objects.all(),request)
        for stored_report in report_page:
            if user.role in ['admin','accountant'] and not request.GET.get('client_id'): payload=stored_report.payload
            else:
                params={'from':stored_report.start.isoformat(),'to':(stored_report.end_exclusive-timedelta(days=1)).isoformat(),'cutoff':stored_report.payload['cutoff']}
                if request.GET.get('client_id'):params['client_id']=request.GET['client_id']
                payload,_=report(user,params)
            result.append({'id':stored_report.pk,'start':stored_report.start.isoformat(),'end_exclusive':stored_report.end_exclusive.isoformat(),'created_at':stored_report.created_at.isoformat(),'payload':payload})
        return {'items':result,'next_cursor':cursor},200
    if route=='notifications' and method=='GET':
        qs=Notification.objects.filter(user=user)
        if request.GET.get('after'):
            after=parse_datetime(request.GET['after'])
            if not after or timezone.is_naive(after): fail('VALIDATION_ERROR','Некорректное after')
            qs=qs.filter(created_at__gt=after)
        return rows(qs,request),200
    if parts[0]=='notifications' and len(parts)==3 and parts[2]=='read':
        Notification.objects.filter(pk=parts[1],user=user).update(read=True); return {'read':True},200
    if route=='audit' and method=='GET': require(user,'admin','accountant'); return rows(AuditEvent.objects.all(),request),200
    if parts[0]=='batches' and len(parts)==3 and parts[2]=='adjust':
        require(user,'admin'); obj=Batch.objects.select_for_update().get(pk=parts[1]);obj._audit_before=snapshot(obj); quantity=data.get('quantity')
        if type(quantity)!=int or quantity<obj.reserved or not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Остаток не может быть ниже резерва; укажите причину')
        StockMovement.objects.create(product=obj.product,batch=obj,quantity=quantity-obj.quantity,disposition='adjustment',reason=data['reason'],actor=user)
        obj.quantity=quantity; obj.save(); audit(user,'batch.adjusted',obj,data); return serialize(obj),200
    if parts[0]=='products' and len(parts)==3 and parts[2]=='update':
        require(user,'admin'); obj=Product.objects.select_for_update().get(pk=parts[1])
        if 'name' in data:
            if not isinstance(data['name'],str) or not data['name'].strip() or len(data['name'])>150: fail('VALIDATION_ERROR','Проверьте название')
            obj.name=data['name'].strip()
        if 'price_amount' in data: obj.price=money(data['price_amount'])
        if 'description' in data: obj.description=str(data['description'])[:5000]
        if 'active' in data:
            if type(data['active'])!=bool: fail('VALIDATION_ERROR','active должен быть boolean')
            obj.active=data['active']
        if 'preparation_minutes' in data:
            if type(data['preparation_minutes'])!=int or not 1<=data['preparation_minutes']<=100000: fail('VALIDATION_ERROR','Некорректное время')
            obj.preparation_minutes=data['preparation_minutes']
        obj.save(); audit(user,'product.updated',obj,data); return serialize(obj),200
    if route=='stock-movements' and method=='GET':
        require(user,'admin','accountant'); return rows(StockMovement.objects.all(),request),200
    if parts[0]=='stock-movements' and len(parts)==3 and parts[2]=='resolve':
        require(user,'admin'); source=StockMovement.objects.select_for_update().get(pk=parts[1])
        if source.disposition!='quarantine' or source.quantity<=0 or source.resolved:fail('INVALID_STATE','Нет неразобранного карантинного остатка',409)
        if data.get('disposition') not in ['available','write_off'] or not str(data.get('reason','')).strip():fail('VALIDATION_ERROR','Нужно решение о пригодности и основание')
        batch=None
        if data['disposition']=='available':
            batch=Batch.objects.select_for_update().get(pk=data.get('batch_id'),product=source.product)
            if batch.expires_at<=timezone.now() or batch.manufactured_at>timezone.now():fail('STOCK_EXPIRED','Возврат в просроченную или будущую партию запрещён',409)
            batch.quantity+=source.quantity; batch.save()
        action=StockMovement.objects.create(product=source.product,batch=batch,quantity=source.quantity,disposition=data['disposition'],source=source,reason=data['reason'],actor=user)
        source.resolved=True; source.save(); audit(user,'stock.quarantine_resolved',action,data);return serialize(action),200
    if parts[0]=='staff' and len(parts)==3 and parts[2]=='role':
        require(user,'admin'); target=User.objects.select_for_update().get(pk=parts[1]);target._audit_before=snapshot(target); role=data.get('role')
        if role not in ['admin','courier','cashier','accountant'] or target.role=='customer': fail('VALIDATION_ERROR','Выберите роль сотрудника')
        if target.pk==user.pk and role!='admin': fail('INVALID_STATE','Нельзя лишить себя прав администратора',409)
        target.role=role; target.save()
        for session in Session.objects.filter(expire_date__gt=timezone.now()):
            if session.get_decoded().get('_auth_user_id')==str(target.pk): session.delete()
        audit(user,'staff.role',target,data); return {'id':str(target.pk),'role':role},200
    return None
