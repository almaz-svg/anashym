from decimal import Decimal
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .models import *
from .services import *

def version_check(order,data):
    from .views import fail
    if data.get('version')!=order.version: fail('VERSION_CONFLICT','Заказ изменился. Обновите данные',409)

def transition(user,order,data):
    from .views import fail
    require(user,'admin','courier'); version_check(order,data)
    target=data.get('status')
    if target=='dispatched': target='out_for_delivery'
    if user.role=='courier' and (target!='out_for_delivery' or order.courier_id!=user.pk or data.get('courier_id')): fail('FORBIDDEN','Курьер может только выехать по своему назначению',403)
    if target=='assigned': target='ready'
    failed_cancellation=target=='cancelled' and order.status=='delivery_failed'
    if failed_cancellation and (Reservation.objects.filter(order=order).exists() or not order.attempts.filter(outcome='failed').exists()):
        fail('INVALID_STATE','Сначала примите весь товар у курьера',409)
    allowed={'submitted':['accepted','cancelled'],'accepted':['preparing','cancelled'],'preparing':['ready','cancelled'],'ready':['out_for_delivery','cancelled'],'delivery_failed':['out_for_delivery','cancelled']}
    assigning=data.get('courier_id') and target==order.status and order.status=='ready'
    if not assigning and target not in allowed.get(order.status,[]): fail('INVALID_STATE','Недопустимый переход статуса',409)
    if data.get('courier_id'):
        try: order.courier=User.objects.get(pk=data['courier_id'],role='courier',is_active=True)
        except User.DoesNotExist: fail('VALIDATION_ERROR','Курьер не найден')
    if target=='ready':
        if order.proposed_delivery_at: fail('INVALID_STATE','Клиент ещё не подтвердил перенос',409)
        if Reservation.objects.filter(order=order,quota__isnull=False).exists(): fail('INVALID_STATE','Предзаказ ещё не обеспечен готовыми партиями',409)
    if target=='out_for_delivery' and not order.courier_id: fail('INVALID_STATE','Сначала назначьте курьера',409)
    if target in ['accepted','preparing','out_for_delivery'] and order.payment_mode=='kaspi':
        Client.objects.select_for_update().get(pk=order.client_id)
        if available_order_prepayment(order)<order.total:
            fail('PAYMENT_REQUIRED','Для заказа нужна полная доступная предоплата Kaspi',409)
    if target=='out_for_delivery':
        if order.status=='delivery_failed':
            for item in order.items.all():
                held=Reservation.objects.filter(order=order,batch__product_id=item.product_id,in_transit=True).aggregate(total=Sum('quantity'))['total'] or 0
                if held!=item.quantity-item.delivered_quantity:
                    fail('STOCK_UNAVAILABLE','У курьера недостаточно товара для повторного выезда',409)
        for reservation in Reservation.objects.select_for_update().filter(order=order,in_transit=False):
            if not reservation.batch_id: fail('INVALID_STATE','Партии ещё не определены',409)
            batch=Batch.objects.select_for_update().get(pk=reservation.batch_id)
            if batch.expires_at<=timezone.now(): fail('STOCK_EXPIRED','Срок партии истёк',409)
            batch.quantity-=reservation.quantity; batch.reserved-=reservation.quantity; batch.save()
            reservation.in_transit=True; reservation.save()
            StockMovement.objects.create(product=batch.product,batch=batch,quantity=-reservation.quantity,disposition='courier',reason='Выезд заказа '+str(order.pk),actor=user)
    if target=='cancelled':
        release_reservations(order)
        if failed_cancellation and order.payment_mode=='deferred':
            # Physical receipt removed custody rows; their credit was held until final cancellation.
            client=Client.objects.select_for_update().get(pk=order.client_id)
            client.reserved_credit-=order.total-order.delivered_total
            client.save(update_fields=['reserved_credit'])
        ensure_cancellation_refund(user,order,str(data.get('reason') or 'Отмена администратором'))
    order.status=target; order.version+=1; order.reservation_expires_at=None; order.save(); audit(user,'order.'+target,order,data)
    return order

def fulfill(user,order,data):
    from .views import fail
    require(user,'admin')
    if 'version' in data:version_check(order,data)
    if order.kind!='preorder' or order.status not in ['accepted','preparing']: fail('INVALID_STATE','Этот заказ нельзя обеспечить партиями',409)
    rows=data.get('batches',[])
    if not rows: fail('VALIDATION_ERROR','Укажите партии')
    for row in rows:
        qty=row.get('quantity')
        if type(qty)!=int or qty<=0: fail('VALIDATION_ERROR','Некорректное количество')
        try: batch=Batch.objects.select_for_update().get(pk=row['batch_id'],product_id=row['product_id'],expires_at__gt=timezone.now(),manufactured_at__lte=timezone.now())
        except Batch.DoesNotExist: fail('VALIDATION_ERROR','Партия недоступна')
        quotas=list(Reservation.objects.select_for_update().filter(order=order,quota__product_id=batch.product_id))
        if sum(r.quantity for r in quotas)<qty or batch.quantity-batch.reserved<qty: fail('STOCK_UNAVAILABLE','Недостаточно квоты или партии',409)
        remaining=qty
        for reservation in quotas:
            take=min(remaining,reservation.quantity)
            quota=Quota.objects.select_for_update().get(pk=reservation.quota_id); quota.reserved-=take; quota.save()
            reservation.quantity-=take
            if reservation.quantity: reservation.save()
            else: reservation.delete()
            remaining-=take
            if not remaining: break
        batch.reserved+=qty; batch.save(); Reservation.objects.create(order=order,batch=batch,quantity=qty)
    order.version+=1; order.save(); audit(user,'order.fulfilled',order,data)
    if Reservation.objects.filter(order=order,quota__isnull=False).exists(): fail('STOCK_UNAVAILABLE','Все позиции предзаказа должны быть обеспечены партиями',409)
    return order

def deliver(user,order,data):
    from .views import fail
    require(user,'courier','admin'); version_check(order,data)
    if user.role=='admin' and not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Администратор указывает основание передачи')
    if (user.role=='courier' and order.courier_id!=user.pk) or order.status!='out_for_delivery': fail('INVALID_STATE','Нет активного назначения',409)
    ids=data.get('photo_ids') or ([data['photo_id']] if data.get('photo_id') else [])
    if not 1<=len(ids)<=5 or Photo.objects.filter(pk__in=ids,order=order,uploaded_by=user,purpose='delivery').count()!=len(ids): fail('PHOTO_REQUIRED','Нужно сохранённое фото передачи')
    rows=data.get('items',[])
    if not isinstance(rows,list) or any(type(r.get('quantity'))!=int or r['quantity']<0 for r in rows): fail('VALIDATION_ERROR','Некорректные количества')
    if set(str(i.product_id) for i in order.items.all())!=set(r.get('product_id') for r in rows) or len(rows)!=order.items.count(): fail('VALIDATION_ERROR','Укажите каждую позицию ровно один раз')
    rows=[r for r in rows if r['quantity']>0]
    if not rows: fail('VALIDATION_ERROR','Укажите принятые позиции')
    charge=ZERO; seen=set()
    for row in rows:
        pid=row.get('product_id'); qty=row.get('quantity')
        if pid in seen or type(qty)!=int or qty<=0: fail('VALIDATION_ERROR','Некорректные позиции')
        seen.add(pid)
        try: item=OrderItem.objects.select_for_update().get(order=order,product_id=pid)
        except OrderItem.DoesNotExist: fail('VALIDATION_ERROR','Позиция отсутствует')
        if item.delivered_quantity+qty>item.quantity: fail('VALIDATION_ERROR','Передача превышает заказ')
        left=qty
        for r in Reservation.objects.select_for_update().filter(order=order,batch__product_id=pid).order_by('id'):
            take=min(left,r.quantity)
            batch=Batch.objects.select_for_update().get(pk=r.batch_id)
            if batch.expires_at<=timezone.now(): fail('STOCK_EXPIRED','Срок годности партии истёк',409)
            if not r.in_transit: fail('INVALID_STATE','Товар не передан курьеру',409)
            r.quantity-=take
            if r.quantity: r.save()
            else: r.delete()
            left-=take
            if not left: break
        if left: fail('STOCK_UNAVAILABLE','Нет резерва на передаваемый товар',409)
        item.delivered_quantity+=qty; item.save(); charge+=qty*item.unit_price
        StockMovement.objects.create(product=item.product,quantity=-qty,disposition='delivery',reason='Передача клиенту',actor=user)
    if order.payment_mode=='cash':
        received=money(data.get('cash_received_amount','0'),False); change=money(data.get('cash_change_amount','0'),False)
        if received<0 or change<0 or change>cash_available(user): fail('CASH_CHANGE_UNAVAILABLE','Недостаточно наличных для сдачи',409)
        net=received-change
        if net<charge: fail('PAYMENT_REQUIRED','Наличная передача требует полного расчёта',409)
        if net>charge and not data.get('advance_consent'): fail('ADVANCE_CONSENT_REQUIRED','Подтвердите зачисление переплаты в аванс')
    if order.payment_mode=='kaspi':
        confirmed=PaymentAllocation.objects.filter(order=order,payment__status='confirmed').aggregate(total=Sum('amount'))['total'] or ZERO
        Client.objects.select_for_update().get(pk=order.client_id)
        available_advance=available_order_prepayment(order)
        if confirmed+available_advance<order.delivered_total+charge: fail('PAYMENT_REQUIRED','Kaspi ещё не подтверждён на полную сумму',409)
    post_ledger(user,order.client,charge,'delivery',order)
    if order.payment_mode=='deferred':
        client=Client.objects.select_for_update().get(pk=order.client_id); client.reserved_credit-=charge; client.save()
    if order.payment_mode=='cash':
        payment=Payment.objects.create(client=order.client,order=order,method='cash',amount=net,actor=user); confirm_payment(user,payment)
    order.delivered_total+=charge
    complete=all(i.delivered_quantity==i.quantity for i in order.items.all())
    if not complete:
        if not str(data.get('reason','')).strip(): fail('VALIDATION_ERROR','Для частичной передачи укажите причину отказа')
        if order.payment_mode=='deferred':
            client=Client.objects.select_for_update().get(pk=order.client_id)
            client.reserved_credit-=sum(r.quantity*order.items.get(product_id=r.batch.product_id).unit_price for r in Reservation.objects.filter(order=order)); client.save()
    order.status='delivered'; order.version+=1; order.save(); allocate_advance(order.client)
    DeliveryAttempt.objects.create(order=order,courier=order.courier,outcome='delivered' if complete else 'partial',items=rows,photo_ids=ids,reason=data.get('reason',''))
    audit(user,'order.delivery',order,{**data,'charged_amount':str(charge)})
    return order
