import hashlib,json,re,uuid
from datetime import timedelta,date
from decimal import Decimal,InvalidOperation
from django.contrib.auth import authenticate,login,logout
from django.db import transaction,IntegrityError
from django.db.models import Sum,F
from django.http import JsonResponse,HttpResponse
from django.http.response import HttpResponseBase
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.core import signing
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from rest_framework.decorators import api_view
from .models import User,Client,DeliveryPoint,Product,Batch,Quota,Order,OrderItem,Reservation,Idempotency,LoginThrottle

class Problem(Exception):
    def __init__(self,code,message,status=422,fields=None,details=None):
        self.code,self.message,self.status,self.fields,self.details=code,message,status,fields or {},details

def fail(code,message,status=422,fields=None,details=None):
    raise Problem(code,message,status,fields,details)

def error(p):
    return JsonResponse({'code':p.code,'message':p.message,'field_errors':p.fields,'details':p.details,'request_id':str(uuid.uuid4())},status=p.status)

def validate(data,required,optional=()):
    if not isinstance(data,dict): fail('VALIDATION_ERROR','Ожидается JSON объект')
    fields={k:['Обязательное поле'] for k in required if k not in data}
    fields.update({k:['Неизвестное поле'] for k in data if k not in set(required)|set(optional)})
    if fields: fail('VALIDATION_ERROR','Проверьте поля',fields=fields)

def me(user):
    client=user.client
    return {'user_id':str(user.id),'role':user.role,'client_id':str(client.id) if client else None,'approval_status':client.approval_status if client else 'active','name':user.first_name or (client.name if client else user.username),'phone':user.username,'client_name':client.name if client else '','must_change_password':user.must_change_password,'client_archived':client.archived if client else False}

def order_data(order):
    from .models import PaymentAllocation, LedgerEntry
    paid=order._paid_amount if hasattr(order,'_paid_amount') else PaymentAllocation.objects.filter(order=order).aggregate(total=Sum('amount'))['total'] or Decimal('0')
    credit=order._credit_amount if hasattr(order,'_credit_amount') else LedgerEntry.objects.filter(order=order,kind='return').aggregate(total=Sum('amount'))['total'] or Decimal('0')
    settlement=max(Decimal('0'),order.delivered_total+credit)
    if not order.delivered_total:
        from .services import available_order_prepayment
        paid=order._available_prepayment if hasattr(order,'_available_prepayment') else available_order_prepayment(order)
    payment_status=('settled' if settlement==0 else 'paid' if paid>=settlement else 'partial' if paid else 'unpaid') if order.delivered_total else ('paid' if paid>=order.total else 'partial' if paid else 'unpaid')
    partial=order.status=='delivered' and any(i.delivered_quantity<i.quantity for i in order.items.all())
    result={'cash_collection_assigned':order.cash_collection_assigned,'partial':partial,'delivered_amount':str(order.delivered_total),'outstanding_amount':str(max(Decimal('0'),settlement-paid)),'return_credit_amount':str(-credit),'settlement_amount':str(settlement),'exchange_id':str(order.exchange_return_id) if order.exchange_return_id else None,'id':str(order.id),'client_id':str(order.client_id),'client_name':order.client.name,'kind':order.kind,'status':order.status,'payment_mode':order.payment_mode,'currency':'KZT','total_amount':f'{order.total:.2f}','delivered_total_amount':str(order.delivered_total),'paid_amount':str(paid),'payment_status':payment_status,'courier_id':str(order.courier_id) if order.courier_id else None,'address_snapshot':json.loads(order.address_snapshot),'proposed_delivery_at':order.proposed_delivery_at.isoformat() if order.proposed_delivery_at else None,'created_at':order.created_at.isoformat(),'requested_delivery_at':order.requested_delivery_at.isoformat(),'reservation_expires_at':order.reservation_expires_at.isoformat() if order.reservation_expires_at else None,'delivery_point_id':str(order.delivery_point_id),'items':[{'product_id':str(i.product_id),'name':i.name,'unit':'portion','quantity':i.quantity,'delivered_quantity':i.delivered_quantity,'returned_quantity':i.returned_quantity,'unit_price_amount':f'{i.unit_price:.2f}','line_total_amount':f'{i.unit_price*i.quantity:.2f}'} for i in order.items.all()],'version':order.version}
    due=order._payment_due_at if hasattr(order,'_payment_due_at') else LedgerEntry.objects.filter(order=order,kind='delivery').order_by('created_at','id').values_list('period__end_exclusive',flat=True).first()
    result['payment_due_at']=due.isoformat() if due else (order.reservation_expires_at.isoformat() if order.payment_mode=='kaspi' and order.reservation_expires_at else None)
    return result


def order_detail(order,user):
    from .models import AuditEvent,Payment,ReturnRequest,Refund,Photo,LedgerEntry
    from .photos import metadata,_allowed
    from .routes import serialize
    from .services import payment_data
    result=order_data(order)
    payments=list(Payment.objects.filter(order=order).select_related('actor','client').prefetch_related('allocations').order_by('created_at','id'))
    returns=list(ReturnRequest.objects.filter(order=order).order_by('created_at','id'))
    refunds=list(Refund.objects.filter(order=order).order_by('created_at','id'))
    ids=[str(order.pk)]+[str(obj.pk) for obj in payments+returns+refunds]+list(LedgerEntry.objects.filter(order=order).values_list('pk',flat=True))
    result['history']=[serialize(e) for e in AuditEvent.objects.filter(object_id__in=[str(i) for i in ids]).order_by('created_at','id')]
    result['photos']=[metadata(photo,user,True) for photo in Photo.objects.filter(order=order).order_by('created_at','id') if _allowed(user,order,photo.purpose)]
    result['delivery_attempts']=[serialize(a) for a in order.attempts.order_by('created_at','id')]
    result['payments']=[payment_data(payment) for payment in payments]
    result['returns']=[serialize(obj) for obj in returns]
    result['refunds']=[serialize(obj) for obj in refunds]
    obligation=next((obj for obj in refunds if obj.source_reference=='cancelled-order:'+str(order.pk)),None)
    result['refund_obligation']={'id':str(obligation.pk),'amount':str(obligation.amount),'status':obligation.status} if obligation else None
    return result


def available(product,now):
    return sum(b.quantity-b.reserved for b in Batch.objects.filter(product=product,expires_at__gt=now,manufactured_at__lte=now))

def listing(request,items):
    try:
        limit=int(request.GET.get('limit',20))
        if not 1<=limit<=100: raise ValueError()
        offset=signing.loads(request.GET['cursor'],salt=request.path,max_age=86400) if request.GET.get('cursor') else 0
        if not isinstance(offset,int) or offset<0: raise ValueError()
    except (ValueError,signing.BadSignature): fail('VALIDATION_ERROR','Некорректная пагинация')
    selected=items[offset:offset+limit]
    return {'items':selected,'next_cursor':signing.dumps(offset+limit,salt=request.path) if len(items)>offset+limit else None}

def place_order(user,data,*,client=None,ai_used=False):
    validate(data,['kind','delivery_point_id','requested_delivery_at','payment_mode','items'],['exchange_id'])
    # Keep the actual actor separate from the customer whose stock/credit is reserved.
    if client is not None and user.role!='admin': fail('FORBIDDEN','Оформление для другого клиента недоступно',403)
    target_client_id=client.pk if client is not None else user.client_id
    if data['kind'] not in ['regular','preorder'] or data['payment_mode'] not in ['deferred','cash','kaspi']: fail('VALIDATION_ERROR','Недопустимый вид заказа или оплаты')
    requested=parse_datetime(str(data['requested_delivery_at']))
    if requested is None or timezone.is_naive(requested): fail('VALIDATION_ERROR','Укажите дату со смещением часового пояса')
    local=timezone.localtime(requested); today=timezone.localdate(); now=timezone.now()
    if (data['kind']=='regular' and local.date()!=today) or (data['kind']=='preorder' and not today<local.date()<=today+timedelta(days=90)): fail('VALIDATION_ERROR','Недопустимая дата доставки')
    try: point=DeliveryPoint.objects.get(id=data['delivery_point_id'],client_id=target_client_id,confirmed=True)
    except (DeliveryPoint.DoesNotExist,ValueError): fail('NOT_FOUND','Точка доставки не найдена',404)
    if not point.window_start<=local.time().replace(tzinfo=None)<=point.window_end: fail('VALIDATION_ERROR','Время вне окна доставки')
    rows=data['items']
    if not isinstance(rows,list) or not 1<=len(rows)<=100: fail('VALIDATION_ERROR','Нужно от 1 до 100 позиций')
    products=[]; seen=set(); total=Decimal('0')
    # Every order locks its organization before stock; deterministic product order prevents deadlocks.
    client=Client.objects.select_for_update().get(id=target_client_id)
    if client.archived or client.approval_status!='active':fail('FORBIDDEN','Новые заказы недоступны для неодобренного или архивного клиента',403)
    if data['payment_mode']=='deferred' and not client.deferred_approved: fail('FORBIDDEN','Отсрочка не одобрена',403)
    from .services import overdue_amount,financial_amounts
    if data['payment_mode']=='deferred' and overdue_amount(client)>0: fail('CREDIT_OVERDUE','Есть просроченная задолженность',409)
    for row in rows:
        validate(row,['product_id','quantity','expected_unit_price'])
        qty=row['quantity']
        if type(qty)!=int or not 1<=qty<=10000: fail('VALIDATION_ERROR','Количество должно быть целым от 1 до 10000')
        if not isinstance(row['product_id'],str): fail('VALIDATION_ERROR','product_id должен быть UUID')
        try: product_id=uuid.UUID(row['product_id'])
        except ValueError: fail('VALIDATION_ERROR','product_id должен быть UUID')
        if product_id in seen: fail('VALIDATION_ERROR','Повтор товара')
        seen.add(product_id)
        try:
            price=Decimal(str(row['expected_unit_price']))
            if not price.is_finite() or price<=0 or price.as_tuple().exponent < -2: raise InvalidOperation()
            product=Product.objects.get(id=product_id,active=True)
        except (InvalidOperation,ValueError,Product.DoesNotExist): fail('VALIDATION_ERROR','Некорректный товар или цена')
        if price!=product.price: fail('PRICE_CHANGED','Цена товара изменилась',409)
        products.append((product,qty)); total+=product.price*qty
    if data['payment_mode']=='deferred' and total>client.credit_limit-financial_amounts(client)['debt']-client.reserved_credit: fail('CREDIT_LIMIT_EXCEEDED','Недостаточно свободного лимита',409)
    allocations=[]
    for product,qty in sorted(products,key=lambda v:str(v[0].id)):
        if data['kind']=='regular':
            sources=list(Batch.objects.select_for_update().filter(product=product,expires_at__gt=now,manufactured_at__lte=now).order_by('expires_at','id'))
        else:
            sources=list(Quota.objects.select_for_update().filter(product=product,date=local.date(),cutoff__gt=now).order_by('id'))
        free=sum(s.quantity-s.reserved for s in sources)
        if qty>free: fail('STOCK_UNAVAILABLE','Недостаточно порций',409,details={'product_id':str(product.id),'available_qty':free})
        left=qty
        for source in sources:
            take=min(left,source.quantity-source.reserved)
            if take: allocations.append((source,take)); left-=take
            if not left: break
    exchange=None
    if data.get('exchange_id'):
        from .models import ReturnRequest
        try: exchange=ReturnRequest.objects.select_for_update().get(pk=data['exchange_id'],order__client=client,status='approved',kind='exchange')
        except ReturnRequest.DoesNotExist: fail('VALIDATION_ERROR','Одобренный обмен не найден')
        if exchange.exchange_orders.exists(): fail('INVALID_STATE','Заказ обмена уже создан',409)
    order=Order.objects.create(client=client,delivery_point=point,address_snapshot=json.dumps({'address':point.address,'recipient':point.recipient,'phone':point.phone}),kind=data['kind'],payment_mode=data['payment_mode'],total=total,requested_delivery_at=requested,reservation_expires_at=now+timedelta(minutes=30 if data['payment_mode']=='kaspi' else 60),exchange_return=exchange)
    for product,qty in products: OrderItem.objects.create(order=order,product=product,name=product.name,quantity=qty,unit_price=product.price)
    for source,take in allocations:
        source.reserved+=take; source.save(update_fields=['reserved'])
        Reservation.objects.create(order=order,batch=source if isinstance(source,Batch) else None,quota=source if isinstance(source,Quota) else None,quantity=take)
    if data['payment_mode']=='deferred': client.reserved_credit+=total; client.save(update_fields=['reserved_credit'])
    from .services import audit
    audit(user,'order.created',order,{'ai_used':True} if ai_used else None)
    return order_data(order),201

def route_request(request,route,data):
    if route.startswith('auth/'):
        from .access_management import handle_access
        handled=handle_access(request,route,data)
        if handled is not None:return handled
    if route=='auth/csrf' and request.method=='GET': get_token(request); return None,204
    if route in ['auth/accept-invitation','auth/activate'] and request.method=='POST':
        validate(data,['token','password'])
        try: payload=signing.loads(data['token'],salt='staff-invite',max_age=86400); staff=User.objects.get(pk=payload['staff'])
        except (signing.BadSignature,User.DoesNotExist,KeyError): fail('VALIDATION_ERROR','Приглашение недействительно или истекло')
        if staff.password!=payload['stamp'] or staff.has_usable_password() or len(str(data['password']))<12: fail('VALIDATION_ERROR','Приглашение использовано либо пароль короче 12 символов')
        staff.set_password(data['password']); staff.save(); return {'accepted':True},200
    if route=='auth/login' and request.method=='POST':
        validate(data,['phone','password'])
        if not isinstance(data['phone'],str) or not isinstance(data['password'],str): fail('VALIDATION_ERROR','Телефон и пароль должны быть строками')
        with transaction.atomic():
            throttles=[]
            scopes=sorted(hashlib.sha256(s.encode()).hexdigest() for s in ['ip:'+request.META.get('REMOTE_ADDR',''),'phone:'+data['phone']])
            for scope in scopes:
                LoginThrottle.objects.get_or_create(scope=scope,defaults={'started_at':timezone.now()})
                throttle=LoginThrottle.objects.select_for_update().get(scope=scope)
                if throttle.started_at<timezone.now()-timedelta(minutes=15): throttle.started_at=timezone.now(); throttle.failures=0
                if throttle.failures>=5: fail('RATE_LIMITED','Слишком много попыток. Повторите через 15 минут',429)
                throttles.append(throttle)
            user=authenticate(request,username=data['phone'],password=data['password'])
            for throttle in throttles:
                if user: throttle.failures=0
                else: throttle.failures+=1
                throttle.save()
        if not user: fail('UNAUTHENTICATED','Неверный телефон или пароль',401)
        login(request,user); return me(user),200
    if route=='auth/register' and request.method=='POST':
        validate(data,['phone','password','name','category','description','expected_order_quantity','expected_order_frequency'],['category_other','preferred_payment_mode','requested_period_days'])
        if data.get('preferred_payment_mode','deferred') not in ['deferred','cash','kaspi'] or data.get('requested_period_days',14) not in [7,14,30]: fail('VALIDATION_ERROR','Проверьте способ оплаты и желаемый период')
        if not re.fullmatch(r'\+[1-9]\d{7,14}',str(data['phone'])): fail('VALIDATION_ERROR','Телефон должен быть в формате E.164')
        if len(str(data['password']))<8: fail('VALIDATION_ERROR','Пароль: минимум 8 символов')
        if data['category'] not in ['coffee_shop','store','restaurant','company','individual','other']: fail('VALIDATION_ERROR','Выберите категорию')
        if data['category']=='other' and not str(data.get('category_other','')).strip(): fail('VALIDATION_ERROR','Опишите категорию «Другое»')
        if type(data['expected_order_quantity'])!=int or not 1<=data['expected_order_quantity']<=1000000: fail('VALIDATION_ERROR','Укажите ожидаемое количество от 1 до 1000000')
        for field in ['name','description','expected_order_frequency']:
            maximum=1000 if field=='description' else 200
            if not isinstance(data[field],str) or not data[field].strip() or len(data[field])>maximum: fail('VALIDATION_ERROR','Заполните описание и частоту в пределах допустимой длины')
        if not isinstance(data.get('category_other',''),str) or len(data.get('category_other',''))>200: fail('VALIDATION_ERROR','Категория: максимум 200 символов')
        with transaction.atomic():
            if User.objects.filter(username=data['phone']).exists(): fail('VALIDATION_ERROR','Телефон уже зарегистрирован')
            client=Client.objects.create(**{k:data[k] for k in ['name','category','description','expected_order_quantity','expected_order_frequency']},category_other=data.get('category_other',''),preferred_payment_mode=data.get('preferred_payment_mode','deferred'),requested_period_days=data.get('requested_period_days',14))
            user=User.objects.create_user(username=data['phone'],password=data['password'],first_name=data['name'][:150],client=client)
        return me(user),201
    user=request.user
    if not user.is_authenticated: fail('UNAUTHENTICATED','Требуется вход',401)
    if route=='auth/me' and request.method=='GET': return me(user),200
    if route=='auth/logout' and request.method=='POST': logout(request); return None,204
    if user.must_change_password:fail('PASSWORD_CHANGE_REQUIRED','Установите новый пароль перед продолжением',403)
    # Parse is a read-only, nonpersistent operation. Bypass the mutation dispatcher,
    # which stores idempotency records, and fail closed until a provider is approved.
    if route in ['ai/order-draft','ai/status']:
        from .services import require
        require(user,'admin')
        if route=='ai/status' and request.method=='GET':
            return {'enabled':False,'reason':'AI_NOT_CONFIGURED'},200
        if route=='ai/order-draft' and request.method=='POST':
            from .ai_drafts import parse_order_message
            return parse_order_message(user,data),200
        fail('NOT_FOUND','Ресурс не найден',404)
    from .routes import handle
    if route=='profile' and request.method=='GET':
        return handle(request,route,data)
    if user.role!='customer' or (user.client_id and user.client.approval_status=='active'):
        if request.method=='POST' and (route!='orders' or user.role=='admin') and not route.startswith('files'):
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                key=request.headers.get('Idempotency-Key')
                if not key: fail('VALIDATION_ERROR','Обязателен Idempotency-Key UUID')
                if key:
                    try: key=uuid.UUID(key)
                    except ValueError: fail('VALIDATION_ERROR','Idempotency-Key должен быть UUID')
                    digest=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
                    old=Idempotency.objects.filter(user=user,method='POST',path=request.path,key=key).first()
                    if old:
                        if old.body_hash!=digest: fail('IDEMPOTENCY_CONFLICT','Ключ уже использован',409)
                        return old.response,old.status
                result=handle(request,route,data)
                if result is not None:
                    if key: Idempotency.objects.create(user=user,method='POST',path=request.path,key=key,body_hash=digest,response=result[0],status=result[1])
                    return result
        else:
            result=handle(request,route,data)
            if result is not None: return result
    if not user.client_id or user.role!='customer' or user.client.approval_status!='active': fail('FORBIDDEN','Доступ ожидает одобрения администратора',403)
    if route=='delivery-points' and request.method=='GET':
        return listing(request,[{'id':str(p.id),'address':p.address,'recipient':p.recipient,'phone':p.phone,'window_start':p.window_start.isoformat(),'window_end':p.window_end.isoformat()} for p in DeliveryPoint.objects.filter(client=user.client,confirmed=True).order_by('id')]),200
    if route=='catalog' and request.method=='GET':
        try:
            day=date.fromisoformat(request.GET.get('delivery_date',''))
            if not timezone.localdate()<=day<=timezone.localdate()+timedelta(days=90): raise ValueError()
        except ValueError: fail('VALIDATION_ERROR','Укажите delivery_date от сегодня до 90 дней')
        from .catalog_read import catalog_products
        from .catalog_details import catalog_rows
        now=timezone.now()
        return listing(request,catalog_rows(catalog_products(day,now),now)),200
    if route=='balance' and request.method=='GET':
        c=user.client; debt=max(c.balance,Decimal('0')); start=c.period_start
        from .services import overdue_amount,financial_amounts
        overdue=overdue_amount(c); amounts=financial_amounts(c); debt=amounts['debt']
        while start+timedelta(days=c.period_days)<=timezone.localdate(): start+=timedelta(days=c.period_days)
        return {'currency':'KZT','balance_amount':f'{c.balance:.2f}','debt_amount':f'{debt:.2f}','advance_amount':f'{amounts["advance"]:.2f}','reserved_refund_amount':f'{amounts["reserved_refund"]:.2f}','overdue_amount':f'{overdue:.2f}','reserved_credit_amount':f'{c.reserved_credit:.2f}','credit_limit_amount':f'{c.credit_limit:.2f}','available_credit_amount':f'{max(c.credit_limit-debt-c.reserved_credit,Decimal("0")):.2f}','period_days':c.period_days,'period_start':start.isoformat(),'period_end_exclusive':(start+timedelta(days=c.period_days)).isoformat()},200
    if route=='orders' and request.method=='GET': return listing(request,[order_data(o) for o in Order.objects.filter(client=user.client).order_by('-created_at','id')]),200
    if route.startswith('orders/') and request.method=='GET':
        try: order=Order.objects.get(id=route.split('/')[1],client=user.client)
        except (Order.DoesNotExist,ValueError): fail('NOT_FOUND','Заказ не найден',404)
        return order_data(order),200
    if route=='orders' and request.method=='POST':
        try: key=uuid.UUID(request.headers.get('Idempotency-Key',''))
        except ValueError: fail('VALIDATION_ERROR','Обязателен Idempotency-Key UUID')
        digest=hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        with transaction.atomic():
            # Serialize all requests for this user before looking up the key.
            User.objects.select_for_update().get(id=user.id)
            Idempotency.objects.filter(created_at__lt=timezone.now()-timedelta(days=7)).delete()
            old=Idempotency.objects.filter(user=user,method=request.method,path=request.path,key=key).first()
            if old:
                if old.body_hash!=digest: fail('IDEMPOTENCY_CONFLICT','Ключ уже использован с другим запросом',409)
                return old.response,old.status
            try:
                with transaction.atomic(): result,status=place_order(user,data)
            except Problem as p:
                result=json.loads(error(p).content); status=p.status
            Idempotency.objects.create(user=user,method=request.method,path=request.path,key=key,body_hash=digest,response=result,status=status)
            return result,status
    fail('NOT_FOUND','Ресурс не найден',404)

@api_view(['GET','POST'])
def endpoint(request,route):
    try:
        data=request.POST.dict() if request.content_type and request.content_type.startswith('multipart/') else json.loads(request.body) if request.body else {}
        response=route_request(request,route.rstrip('/'),data)
        if isinstance(response,HttpResponseBase): return response
        result,status=response
        return HttpResponse(status=204) if status==204 else JsonResponse(result,status=status)
    except (json.JSONDecodeError,UnicodeDecodeError): return error(Problem('VALIDATION_ERROR','Некорректный JSON'))
    except IntegrityError:
        if route.rstrip('/')=='auth/register': return error(Problem('VALIDATION_ERROR','Телефон уже зарегистрирован'))
        return error(Problem('CONFLICT','Операция конфликтует с уже сохранёнными данными',409))
    except ObjectDoesNotExist: return error(Problem('NOT_FOUND','Ресурс не найден',404))
    except (ValidationError,TypeError,AttributeError,OverflowError,ValueError,KeyError): return error(Problem('VALIDATION_ERROR','Некорректные значения полей'))
    except Problem as p: return error(p)

# DRF exempts API views by default; login and anonymous registration still require CSRF.
endpoint.csrf_exempt=False

def csrf_failure(request,reason=''):
    return error(Problem('FORBIDDEN','CSRF проверка не пройдена. Обновите страницу',403))


