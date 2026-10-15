"""Independent regression acceptance for finance, scope and delivery edges."""
import uuid
import importlib
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.apps import apps
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Client, User, DeliveryPoint, Product, Order, OrderItem, LedgerEntry, Payment, Photo, ReturnRequest, Batch, Reservation, StockMovement


class FinanceEdgeTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.customer = Client.objects.create(name='Review client', approval_status='active', deferred_approved=True, credit_limit=50000, period_start=timezone.localdate()-timedelta(days=28))
        self.admin = User.objects.create_user(username='review-admin', role='admin')
        self.courier = User.objects.create_user(username='review-courier', role='courier')
        self.cashier = User.objects.create_user(username='review-cashier', role='cashier')
        self.other_cashier = User.objects.create_user(username='review-other-cashier', role='cashier')
        self.point = DeliveryPoint.objects.create(client=self.customer,address='Review address',recipient='Review',phone='+77000000000')
        self.product = Product.objects.create(name='Review cake',price=1500)

    def post(self, path, data):
        return self.api.post('/api/v1/'+path, data, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def order(self, status='delivered', mode='deferred', when=None):
        obj=Order.objects.create(client=self.customer,delivery_point=self.point,address_snapshot='{}',kind='regular',status=status,payment_mode=mode,total=1500,delivered_total=1500 if status=='delivered' else 0,courier=self.courier,requested_delivery_at=when or timezone.now())
        OrderItem.objects.create(order=obj,product=self.product,name=self.product.name,quantity=1,unit_price=1500,delivered_quantity=1 if status=='delivered' else 0)
        return obj

    def entry(self, order, amount, kind, when):
        entry=LedgerEntry.objects.create(client=self.customer,order=order,amount=amount,kind=kind,actor=self.admin,reference=str(uuid.uuid4()))
        LedgerEntry.objects.filter(pk=entry.pk).update(created_at=when)
        return entry

    def test_late_payment_reduces_previous_period_current_outstanding(self):
        old=timezone.now()-timedelta(days=20)
        order=self.order(when=old)
        self.entry(order,1500,'delivery',old)
        self.customer.balance=1500; self.customer.save()
        self.api.force_authenticate(self.admin)
        closed=self.post('periods/close',{'as_of':timezone.localdate().isoformat()})
        self.assertEqual(closed.status_code,200,closed.content)
        original=min(self.api.get('/api/v1/periods').json()['items'],key=lambda row:row['start'])['snapshot']
        payment=self.post('payments',{'client_id':str(self.customer.pk),'method':'kaspi','amount':'1500','reference':'late-review'}).json()
        response=self.post('payments/'+payment['id']+'/confirm',{'reason':'Review verified'})
        self.assertEqual(response.status_code,200,response.content)
        response=self.api.get('/api/v1/periods')
        old_period=min(response.json()['items'],key=lambda row:row['start'])
        self.assertEqual(Decimal(old_period['current_outstanding_amount']),Decimal('0'))
        self.assertEqual(old_period['snapshot'],original)

    def test_cashier_report_does_not_expose_other_cashier_payment(self):
        order=self.order()
        self.entry(order,-777,'payment',timezone.now())
        Payment.objects.create(client=self.customer,order=order,method='cash',amount=777,status='confirmed',actor=self.other_cashier,confirmed_at=timezone.now())
        self.api.force_authenticate(self.cashier)
        day=timezone.localdate().isoformat()
        response=self.api.get('/api/v1/reports',{'from':day,'to':day})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Decimal(response.json()['totals']['paid_amount']),Decimal('0'))

    def test_cash_shortage_can_be_resolved_by_admin_deferred_conversion(self):
        order=self.order(status='out_for_delivery',mode='cash')
        self.api.force_authenticate(self.admin)
        response=self.post('orders/'+str(order.pk)+'/payment-mode',{'payment_mode':'deferred','reason':'Approved shortage','version':1})
        self.assertEqual(response.status_code,200,response.content)

    def test_failed_delivery_cannot_cancel_away_physical_goods(self):
        order=self.order(status='delivery_failed')
        self.api.force_authenticate(self.admin)
        response=self.post('orders/'+str(order.pk)+'/transition',{'status':'cancelled','reason':'Cannot erase courier custody','version':1})
        self.assertEqual(response.status_code,409,response.content)

    def test_receive_return_rejects_delivery_photo_as_evidence(self):
        order=self.order()
        ret=ReturnRequest.objects.create(order=order,items=[{'product_id':str(self.product.pk),'quantity':1}],reason='Broken',amount=1500)
        photo=Photo.objects.create(order=order,uploaded_by=self.courier,purpose='delivery',file='review-existing.png',content_hash='a'*64,mime='image/png',size=1)
        self.api.force_authenticate(self.admin)
        response=self.post('returns/'+str(ret.pk)+'/receive',{'reason':'Receiving return','photo_ids':[str(photo.pk)]})
        self.assertEqual(response.status_code,422,response.content)

    def test_fifo_follows_delivery_obligation_not_order_creation(self):
        newer_delivery=self.order(when=timezone.now()-timedelta(days=1))
        older_delivery=self.order(when=timezone.now()-timedelta(days=20))
        Order.objects.filter(pk=newer_delivery.pk).update(created_at=timezone.now()-timedelta(days=25))
        self.entry(newer_delivery,1500,'delivery',timezone.now()-timedelta(days=1))
        self.entry(older_delivery,1500,'delivery',timezone.now()-timedelta(days=20))
        self.customer.balance=3000; self.customer.save()
        self.api.force_authenticate(self.admin)
        payment=self.post('payments',{'client_id':str(self.customer.pk),'method':'kaspi','amount':'1500','reference':'fifo-review'}).json()
        response=self.post('payments/'+payment['id']+'/confirm',{'reason':'Review verified'})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['allocations'][0]['order_id'],str(older_delivery.pk))

    def test_assigned_courier_can_dispatch_ready_order(self):
        order=self.order(status='ready')
        self.api.force_authenticate(self.courier)
        response=self.post('orders/'+str(order.pk)+'/transition',{'status':'out_for_delivery','version':1})
        self.assertEqual(response.status_code,200,response.content)

    def test_shift_opening_float_and_other_cashier_are_separate(self):
        self.api.force_authenticate(self.cashier)
        opened=self.post('shifts',{'action':'open','opening_amount':'1000'})
        self.assertEqual(opened.status_code,200,opened.content)
        issued=self.post('cash-movements',{'courier_id':str(self.courier.pk),'amount':'300','direction':'issue','reason':'Float'})
        self.assertEqual(issued.status_code,201,issued.content)
        self.api.force_authenticate(self.other_cashier)
        other=self.post('shifts',{'action':'open','opening_amount':'9000'})
        self.assertEqual(other.status_code,200,other.content)
        self.api.force_authenticate(self.cashier)
        closed=self.post('shifts',{'action':'close','actual_amount':'700'})
        self.assertEqual(closed.status_code,200,closed.content)
        self.assertEqual(Decimal(closed.json()['expected_amount']),Decimal('700'))
        listing=self.api.get('/api/v1/shifts').json()['items']
        self.assertTrue(all(row['cashier_id']==str(self.cashier.pk) for row in listing))

    def test_credit_return_releases_payment_allocation_and_receipt_does_not_recredit(self):
        order=self.order()
        self.entry(order,1500,'delivery',timezone.now())
        self.customer.balance=1500; self.customer.save()
        self.api.force_authenticate(self.admin)
        payment=self.post('payments',{'client_id':str(self.customer.pk),'order_id':str(order.pk),'method':'kaspi','amount':'1500','reference':'return-review'}).json()
        self.assertEqual(self.post('payments/'+payment['id']+'/confirm',{'reason':'Verified'}).status_code,200)
        ret=ReturnRequest.objects.create(order=order,items=[{'product_id':str(self.product.pk),'quantity':1}],reason='Broken',amount=1500)
        decision=self.post('returns/'+str(ret.pk)+'/decide',{'decision':'approve','without_collection':True,'reason':'Accept without collection'})
        self.assertEqual(decision.status_code,200,decision.content)
        payment_obj=Payment.objects.get(pk=payment['id'])
        self.assertEqual(sum(payment_obj.allocations.values_list('amount',flat=True)),0)
        photo=Photo.objects.create(order=order,uploaded_by=self.admin,purpose='return',file='review-return.png',content_hash='b'*64,mime='image/png',size=1)
        received=self.post('returns/'+str(ret.pk)+'/receive',{'photo_ids':[str(photo.pk)],'reason':'Later receipt'})
        self.assertEqual(received.status_code,200,received.content)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.balance,Decimal('-1500'))
        self.assertEqual(LedgerEntry.objects.filter(order=order,kind='return').count(),1)

    def test_refunded_advance_cannot_pay_future_delivery(self):
        self.api.force_authenticate(self.admin)
        payment=self.post('payments',{'client_id':str(self.customer.pk),'method':'kaspi','amount':'1500','reference':'refunded-review'}).json()
        self.assertEqual(self.post('payments/'+payment['id']+'/confirm',{'reason':'Verified'}).status_code,200)
        refund=self.post('refunds',{'client_id':str(self.customer.pk),'amount':'1500','method':'kaspi','reason':'Return advance'}).json()
        self.assertEqual(self.post('refunds/'+refund['id']+'/confirm',{'reference':'returned-review'}).status_code,200)
        order=self.order(status='out_for_delivery')
        batch=Batch.objects.create(product=self.product,quantity=0,manufactured_at=timezone.now()-timedelta(hours=1),expires_at=timezone.now()+timedelta(days=1))
        Reservation.objects.create(order=order,batch=batch,quantity=1,in_transit=True)
        self.customer.reserved_credit=1500; self.customer.save()
        self.api.force_authenticate(self.courier)
        photo=Photo.objects.create(order=order,uploaded_by=self.courier,purpose='delivery',file='review-future.png',content_hash='c'*64,mime='image/png',size=1)
        response=self.post('orders/'+str(order.pk)+'/delivery',{'version':1,'photo_ids':[str(photo.pk)],'items':[{'product_id':str(self.product.pk),'quantity':1}]})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(Decimal(response.json()['outstanding_amount']),Decimal('1500'))

    def test_quarantine_release_is_bounded_and_cannot_repeat(self):
        self.api.force_authenticate(self.admin)
        batch=Batch.objects.create(product=self.product,quantity=10,manufactured_at=timezone.now()-timedelta(hours=1),expires_at=timezone.now()+timedelta(days=1))
        source=StockMovement.objects.create(product=self.product,quantity=2,disposition='quarantine',reason='Physical receipt',actor=self.admin)
        response=self.post('stock-movements/'+str(source.pk)+'/resolve',{'disposition':'available','batch_id':batch.pk,'reason':'Inspected safe'})
        self.assertEqual(response.status_code,200,response.content)
        repeat=self.post('stock-movements/'+str(source.pk)+'/resolve',{'disposition':'available','batch_id':batch.pk,'reason':'Repeated request'})
        self.assertEqual(repeat.status_code,409,repeat.content)
        batch.refresh_from_db()
        self.assertEqual(batch.quantity,12)
        self.assertEqual(StockMovement.objects.filter(source=source).count(),1)

    def test_quarantine_cannot_enter_other_product_batch(self):
        self.api.force_authenticate(self.admin)
        other=Product.objects.create(name='Other cake',price=1600)
        batch=Batch.objects.create(product=other,quantity=10,manufactured_at=timezone.now()-timedelta(hours=1),expires_at=timezone.now()+timedelta(days=1))
        source=StockMovement.objects.create(product=self.product,quantity=2,disposition='quarantine',reason='Physical receipt',actor=self.admin)
        response=self.post('stock-movements/'+str(source.pk)+'/resolve',{'disposition':'available','batch_id':batch.pk,'reason':'Wrong product'})
        self.assertIn(response.status_code,[404,422],response.content)
        batch.refresh_from_db(); source.refresh_from_db()
        self.assertEqual(batch.quantity,10)
        self.assertFalse(source.resolved)

    def test_legacy_ledger_period_backfill_is_idempotent(self):
        from .models import Period
        old=timezone.now()-timedelta(days=20)
        order=self.order(when=old)
        entry=self.entry(order,1500,'delivery',old)
        migrate=importlib.import_module('shop.migrations.0012_backfill_ledger_periods')
        migrate.backfill(apps,None)
        entry.refresh_from_db()
        self.assertIsNotNone(entry.period_id)
        original=entry.period_id
        self.assertLessEqual(entry.period.start,timezone.localtime(old).date())
        self.assertGreater(entry.period.end_exclusive,timezone.localtime(old).date())
        count=Period.objects.count()
        migrate.backfill(apps,None)
        entry.refresh_from_db()
        self.assertEqual(entry.period_id,original)
        self.assertEqual(Period.objects.count(),count)
