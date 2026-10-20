from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from shop.models import Client,Order,Reservation,Batch,Quota,User
from shop.services import audit,ensure_cancellation_refund,available_order_prepayment

class Command(BaseCommand):
    help='Release expired submitted order reservations, safely on repeated runs'
    def handle(self,*args,**options):
        count=0
        for oid,cid in Order.objects.filter(Q(status='submitted')|Q(status='accepted',payment_mode='kaspi'),reservation_expires_at__lte=timezone.now()).values_list('id','client_id'):
            with transaction.atomic():
                order=Order.objects.select_for_update().get(id=oid)
                client=Client.objects.select_for_update().get(id=cid)
                if order.status not in ['submitted','accepted'] or not order.reservation_expires_at or order.reservation_expires_at>timezone.now(): continue
                if order.status=='accepted' and (order.payment_mode!='kaspi' or available_order_prepayment(order)>=order.total):continue
                previous_status=order.status
                for reserve in Reservation.objects.filter(order=order).order_by('batch_id','quota_id'):
                    model=Batch if reserve.batch_id else Quota
                    source=model.objects.select_for_update().get(id=reserve.batch_id or reserve.quota_id)
                    source.reserved-=reserve.quantity; source.save(update_fields=['reserved'])
                    reserve.delete()
                if order.payment_mode=='deferred': client.reserved_credit-=order.total; client.save(update_fields=['reserved_credit'])
                order.status='cancelled'; order.version+=1; order.save(update_fields=['status','version'])
                actor=User.objects.filter(role='admin',is_active=True).first() or User.objects.filter(client=client).first()
                if actor:
                    ensure_cancellation_refund(actor,order,'Истёк срок резерва заказа')
                    audit(actor,'order.reservation_expired',order,{'before':{'status':previous_status},'after':{'status':'cancelled'},'reason':'Истёк срок резерва заказа'})
                count+=1
        self.stdout.write(f'Expired {count} orders')
