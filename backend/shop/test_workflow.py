from django.test import TestCase
from . import tests as slice_tests
from .models import User,Photo,Client,LedgerEntry,Order,OrderItem,Payment,Handover
from decimal import Decimal
from django.core.files.base import ContentFile
import uuid

class WorkflowTests(TestCase):
    setUp=slice_tests.SliceTests.setUp
    body=slice_tests.SliceTests.body
    create=slice_tests.SliceTests.create
    def test_staff_order_visibility_and_transition(self):
        order=self.create().json()
        self.api.force_authenticate(User.objects.get(role='admin'))
        result=self.api.post('/api/v1/orders/'+order['id']+'/transition',{'status':'accepted','version':1},format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(result.status_code,200,result.content)
        self.assertEqual(result.json()['status'],'accepted')

    def test_kaspi_pending_does_not_change_balance(self):
        order=self.create().json()
        photo=Photo.objects.create(order_id=order['id'],uploaded_by=User.objects.get(role='customer'),purpose='payment',file='private/test-receipt.png',content_hash='p'*64,mime='image/png',size=1)
        response=self.api.post('/api/v1/payments',{'order_id':order['id'],'proof_id':str(photo.pk),'method':'kaspi','amount':'1000.00','reference':'test-reference'},format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(self.api.get('/api/v1/balance').json()['balance_amount'],'0.00')

    def post(self,path,body):
        return self.api.post('/api/v1/'+path,body,format='json',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def delivered_order(self,mode='deferred',quantity=10):
        body=self.body(quantity); body['payment_mode']=mode
        response=self.create(body); self.assertEqual(response.status_code,201,response.content); order=response.json()
        admin=User.objects.get(role='admin'); courier=User.objects.get(role='courier')
        self.api.force_authenticate(admin)
        for status in ['accepted','preparing','ready','dispatched']:
            r=self.post('orders/'+order['id']+'/transition',{'status':status,'courier_id':str(courier.pk),'version':order['version']}); self.assertEqual(r.status_code,200,r.content); order=r.json()
        self.api.force_authenticate(courier)
        photo=Photo.objects.create(order_id=order['id'],uploaded_by=courier,purpose='delivery',file=ContentFile(b'test',name='image.png'),content_hash='x'*64,mime='image/png',size=4)
        data={'version':order['version'],'photo_ids':[str(photo.pk)],'items':[{'product_id':order['items'][0]['product_id'],'quantity':quantity}]}
        if mode=='cash': data.update(cash_received_amount=str(quantity*1500),cash_change_amount='0')
        result=self.post('orders/'+order['id']+'/delivery',data); self.assertEqual(result.status_code,200,result.content)
        return result.json()

    def test_full_financial_story_and_handover_does_not_reduce_debt(self):
        order=self.delivered_order(); client=Client.objects.first(); self.assertEqual(client.balance,Decimal('15000'))
        courier=User.objects.get(role='courier')
        self.api.force_authenticate(User.objects.get(role='admin')); self.post('orders/'+order['id']+'/assign-collection',{'courier_id':str(courier.pk),'reason':'Сбор долга'}); self.api.force_authenticate(courier)
        cashphoto=Photo.objects.create(order_id=order['id'],uploaded_by=courier,purpose='cash',file=ContentFile(b'x',name='cash.png'),content_hash='c'*64,mime='image/png',size=1)
        r=self.post('payments',{'client_id':str(client.pk),'order_id':order['id'],'method':'cash','amount':'10000','photo_ids':[str(cashphoto.pk)]}); self.assertEqual(r.status_code,201,r.content)
        client.refresh_from_db(); self.assertEqual(client.balance,Decimal('5000'))
        handover=self.post('handovers',{'amount':'10000'}); self.assertEqual(handover.status_code,201,handover.content)
        self.assertEqual(self.post('handovers',{'amount':'1'}).status_code,409)
        self.api.force_authenticate(User.objects.get(role='cashier'))
        r=self.post('handovers/'+handover.json()['id']+'/confirm',{'amount':'10000'}); self.assertEqual(r.status_code,200,r.content)
        client.refresh_from_db(); self.assertEqual(client.balance,Decimal('5000'))
        self.api.force_authenticate(User.objects.get(role='customer'))
        customer=User.objects.get(role='customer'); retphoto=Photo.objects.create(order_id=order['id'],uploaded_by=customer,purpose='return',file=ContentFile(b'x',name='return.png'),content_hash='r'*64,mime='image/png',size=1)
        r=self.post('returns',{'order_id':order['id'],'items':[{'product_id':order['items'][0]['product_id'],'quantity':1}],'reason':'Повреждение','photo_ids':[str(retphoto.pk)]}); self.assertEqual(r.status_code,201,r.content)
        self.api.force_authenticate(User.objects.get(role='admin'))
        r=self.post('returns/'+r.json()['id']+'/decide',{'decision':'approve','reason':'Без изъятия','without_collection':True}); self.assertEqual(r.status_code,200,r.content)
        client.refresh_from_db(); self.assertEqual(client.balance,Decimal('3500'))
        p=self.post('payments',{'client_id':str(client.pk),'method':'kaspi','amount':'3500','reference':'story'}); self.assertEqual(p.status_code,201,p.content)
        r=self.post('payments/'+p.json()['id']+'/confirm',{'reason':'Verified by administrator'}); self.assertEqual(r.status_code,200,r.content)
        client.refresh_from_db(); self.assertEqual(client.balance,0)
        self.assertEqual(sum(LedgerEntry.objects.values_list('amount',flat=True)),0)

    def test_cash_delivery_full_payment_and_advance_refund(self):
        order=self.delivered_order('cash',1); client=Client.objects.first(); self.assertEqual(client.balance,0)
        self.api.force_authenticate(User.objects.get(role='admin'))
        p=self.post('payments',{'client_id':str(client.pk),'method':'kaspi','amount':'1000','reference':'advance'}).json()
        self.post('payments/'+p['id']+'/confirm',{'reason':'Verified by administrator'})
        refund=self.post('refunds',{'client_id':str(client.pk),'amount':'1000','method':'kaspi','reason':'Возврат аванса'}); self.assertEqual(refund.status_code,201,refund.content)
        r=self.post('refunds/'+refund.json()['id']+'/confirm',{'reason':'Verified by administrator'}); self.assertEqual(r.status_code,200,r.content)
        client.refresh_from_db(); self.assertEqual(client.balance,0)

    def test_partial_finalizes_releases_limit_and_quarantines_remainder(self):
        order=self.delivered_order(quantity=1)
        # Separate larger order: deliver one portion, refuse the other, preserve price.
        self.api.force_authenticate(User.objects.get(role='customer'))
        response=self.create(self.body(2)); order=response.json()
        self.api.force_authenticate(User.objects.get(role='admin')); courier=User.objects.get(role='courier')
        for status in ['accepted','preparing','ready','out_for_delivery']:
            order=self.post('orders/'+order['id']+'/transition',{'status':status,'courier_id':str(courier.pk),'version':order['version']}).json()
        self.api.force_authenticate(courier); photo=Photo.objects.create(order_id=order['id'],uploaded_by=courier,purpose='delivery',file=ContentFile(b'x',name='x.png'),content_hash='y'*64,mime='image/png',size=1)
        r=self.post('orders/'+order['id']+'/delivery',{'version':order['version'],'photo_ids':[str(photo.pk)],'items':[{'product_id':order['items'][0]['product_id'],'quantity':1}],'reason':'Отказ от одной порции'})
        self.assertEqual(r.status_code,200,r.content); self.assertTrue(r.json()['partial']); self.assertEqual(r.json()['status'],'delivered')
        self.assertEqual(Client.objects.first().reserved_credit,0)

    def test_staff_cash_wallet_endpoint(self):
        self.api.force_authenticate(User.objects.get(role='courier'))
        r=self.api.get('/api/v1/cash'); self.assertEqual(r.status_code,200,r.content); self.assertEqual(r.json()['cash_amount'],'0.00')

    def test_financial_role_order_has_no_delivery_contacts(self):
        order=self.create().json(); self.api.force_authenticate(User.objects.get(role='accountant'))
        response=self.api.get('/api/v1/orders/'+order['id'])
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['address_snapshot'],{})
