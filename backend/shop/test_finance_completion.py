"""Financial correction, cancellation, and live debt contract regressions."""
import uuid
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Client, User, DeliveryPoint, Order, Payment, PaymentAllocation, LedgerEntry, Period, Refund, CashMovement, CashboxMovement, AuditEvent
from .services import confirm_payment, post_ledger


class FinancialCompletionTests(TestCase):
    def setUp(self):
        self.customer = Client.objects.create(name='Finance', approval_status='active', deferred_approved=True, credit_limit=10000, period_start=timezone.localdate()-timedelta(days=28))
        self.admin = User.objects.create_user(username='finance-admin', role='admin')
        self.cashier = User.objects.create_user(username='finance-cashier', role='cashier')
        self.user = User.objects.create_user(username='finance-client', client=self.customer)
        self.point = DeliveryPoint.objects.create(client=self.customer, address='Address', recipient='Recipient', phone='+77010000001')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def order(self, delivered=False):
        return Order.objects.create(client=self.customer, delivery_point=self.point, address_snapshot='{}', kind='regular', payment_mode='kaspi', total=100, delivered_total=100 if delivered else 0, status='delivered' if delivered else 'submitted', requested_delivery_at=timezone.now())

    def payment(self, order=None, method='kaspi', actor=None):
        payment = Payment.objects.create(client=self.customer, order=order, amount=100, method=method, reference=str(uuid.uuid4()), actor=actor or self.cashier)
        confirm_payment(self.cashier, payment)
        return payment

    def post(self, path, body):
        return self.api.post('/api/v1/'+path, body, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def test_admin_kaspi_confirmation_requires_reason_but_cashier_does_not(self):
        payment = Payment.objects.create(client=self.customer, amount=100, method='kaspi', reference='mandatory-reason', actor=self.user)
        denied = self.post(f'payments/{payment.pk}/confirm', {})
        self.assertEqual(denied.status_code, 422, denied.content)
        self.api.force_authenticate(self.cashier)
        self.assertEqual(self.post(f'payments/{payment.pk}/confirm', {}).status_code, 200)

    def test_reversal_restores_debt_clears_allocation_and_appends_linked_entry_once(self):
        order = self.order(True)
        post_ledger(self.admin, self.customer, Decimal('100'), 'delivery', order)
        payment = self.payment(order)
        original = LedgerEntry.objects.get(reference='payment:'+str(payment.pk))
        result = self.post(f'payments/{payment.pk}/reverse', {'reason':'Wrong receipt'})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(result.json()['status'], 'reversed')
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.balance, Decimal('100'))
        self.assertFalse(PaymentAllocation.objects.filter(payment=payment).exists())
        correction = LedgerEntry.objects.get(reverses_entry=original)
        self.assertEqual(correction.amount, Decimal('100'))
        self.assertEqual(correction.reason, 'Wrong receipt')
        self.assertEqual(LedgerEntry.objects.get(pk=original.pk).amount, Decimal('-100'))
        again = self.post(f'payments/{payment.pk}/reverse', {'reason':'Retry'})
        self.assertEqual(again.status_code, 409)
        report = self.api.get('/api/v1/reports').json()
        self.assertEqual(report['totals']['paid_amount'], '0.00')
        self.assertEqual(report['totals']['net_amount'], '100.00')
        event = AuditEvent.objects.get(action='payment.reversed')
        self.assertEqual(event.before['status'], 'confirmed')
        self.assertEqual(event.after['status'], 'reversed')

    def test_cancellation_creates_pending_obligation_without_returning_money(self):
        order = self.order()
        self.payment(order)
        self.api.force_authenticate(self.user)
        result = self.post(f'orders/{order.pk}/transition', {'status':'cancelled', 'version':1})
        self.assertEqual(result.status_code, 200, result.content)
        refund = Refund.objects.get(order=order)
        self.assertEqual(refund.status, 'pending')
        self.assertEqual(refund.amount, Decimal('100'))
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.balance, Decimal('-100'))
        self.assertFalse(LedgerEntry.objects.filter(kind='refund').exists())

    def test_cancel_already_refunded_payment_does_not_create_second_obligation(self):
        order = self.order()
        self.payment(order)
        refund = self.post('refunds', {'client_id':str(self.customer.pk), 'amount':'100', 'method':'kaspi', 'reason':'Refund before cancel'})
        self.assertEqual(refund.status_code, 201, refund.content)
        self.assertEqual(self.post('refunds/'+refund.json()['id']+'/confirm', {}).status_code, 200)
        result = self.post(f'orders/{order.pk}/transition', {'status':'cancelled', 'version':1})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(Refund.objects.count(), 1)

    def test_stale_overdue_is_ignored_by_balance_and_profile(self):
        self.customer.overdue = 999
        self.customer.save(update_fields=['overdue'])
        self.api.force_authenticate(self.user)
        self.assertEqual(self.api.get('/api/v1/balance').json()['overdue_amount'], '0.00')
        self.assertEqual(self.api.get('/api/v1/profile').json()['balance']['overdue_amount'], '0.00')

    def test_ledger_cursor_reaches_every_entry_without_truncation(self):
        for index in range(7):
            post_ledger(self.admin, self.customer, Decimal('1'), 'adjustment', reference='page:'+str(index))
        found=[]; cursor=None
        for _ in range(5):
            params={'limit':2}
            if cursor:params['cursor']=cursor
            response=self.api.get('/api/v1/ledger', params)
            self.assertEqual(response.status_code, 200, response.content)
            page=response.json()
            self.assertLessEqual(len(page['items']), 2)
            found.extend(row['id'] for row in page['items'])
            cursor=page['next_cursor']
            if not cursor:break
        self.assertEqual(len(found), 7)
        self.assertEqual(len(set(found)), 7)

    def test_cancellation_refund_consumes_its_order_prepayment_not_another_order(self):
        first=self.order(); second=self.order()
        self.payment(first); self.payment(second)
        self.assertEqual(self.post(f'orders/{second.pk}/transition',{'status':'cancelled','version':1}).status_code,200)
        refund=Refund.objects.get(order=second)
        self.assertEqual(self.post(f'refunds/{refund.pk}/confirm',{}).status_code,200)
        first_payload=self.api.get(f'/api/v1/orders/{first.pk}').json()
        self.assertEqual(Decimal(first_payload['paid_amount']),Decimal('100'))
        self.assertEqual(first_payload['payment_status'],'paid')
        second_payload=self.api.get(f'/api/v1/orders/{second.pk}').json()
        self.assertEqual(Decimal(second_payload['paid_amount']),Decimal('0'))

    def test_cashier_report_includes_admin_correction_of_their_payment(self):
        payment=self.payment(method='cash')
        self.assertEqual(self.post(f'payments/{payment.pk}/reverse',{'reason':'Wrong cash receipt'}).status_code,200)
        self.api.force_authenticate(self.cashier)
        report=self.api.get('/api/v1/reports').json()
        self.assertEqual(report['totals']['paid_amount'],'0.00')
        self.assertEqual(sum(CashboxMovement.objects.filter(cashier=self.cashier).values_list('amount',flat=True)),Decimal('0'))

    def test_courier_reversal_respects_pending_cash_handover(self):
        from .models import Handover
        courier=User.objects.create_user(username='finance-courier',role='courier')
        payment=self.payment(method='cash',actor=courier)
        Handover.objects.create(courier=courier,amount=100)
        response=self.post(f'payments/{payment.pk}/reverse',{'reason':'Mistake'})
        self.assertEqual(response.status_code,409,response.content)
        self.assertEqual(response.json()['code'],'CASH_UNAVAILABLE')
        self.assertEqual(sum(CashMovement.objects.filter(courier=courier).values_list('amount',flat=True)),Decimal('100'))
        payment.refresh_from_db();self.assertEqual(payment.status,'confirmed')

    def test_reversal_reallocates_real_remaining_advance(self):
        order=self.order(True)
        post_ledger(self.admin,self.customer,Decimal('100'),'delivery',order)
        original=self.payment(order)
        backup=self.payment()
        self.assertEqual(self.post(f'payments/{original.pk}/reverse',{'reason':'Duplicate receipt'}).status_code,200)
        self.assertEqual(PaymentAllocation.objects.get(payment=backup,order=order).amount,Decimal('100'))
        self.customer.refresh_from_db();self.assertEqual(self.customer.balance,Decimal('0'))

    def test_reports_paginate_rows_but_preserve_complete_totals_and_csv(self):
        for index in range(5):post_ledger(self.admin,self.customer,Decimal('10'),'delivery',reference='report-page:'+str(index))
        result=self.api.get('/api/v1/reports',{'limit':2}).json()
        self.assertEqual(len(result['items']),2)
        self.assertIsNotNone(result['next_cursor'])
        self.assertEqual(result['totals']['delivered_amount'],'50.00')
        csv=self.api.get('/api/v1/reports',{'limit':2,'format':'csv'})
        self.assertEqual(len(csv.content.decode('utf-8-sig').splitlines()),6)

    def test_pending_refund_is_reserved_when_another_delivery_creates_debt(self):
        from .services import allocate_advance
        prepaid=self.order();self.payment(prepaid)
        self.assertEqual(self.post(f'orders/{prepaid.pk}/transition',{'status':'cancelled','version':1}).status_code,200)
        later=self.order(True)
        post_ledger(self.admin,self.customer,Decimal('100'),'delivery',later)
        allocate_advance(self.customer)
        self.assertFalse(PaymentAllocation.objects.filter(order=later).exists())
        self.api.force_authenticate(self.user)
        balance=self.api.get('/api/v1/balance').json()
        self.assertEqual(balance['debt_amount'],'100.00')
        self.assertEqual(balance['reserved_refund_amount'],'100.00')
        self.assertEqual(balance['advance_amount'],'0.00')
        self.api.force_authenticate(self.admin)
        refund=Refund.objects.get(order=prepaid)
        self.assertEqual(self.post(f'refunds/{refund.pk}/confirm',{}).status_code,200)
        self.customer.refresh_from_db();self.assertEqual(self.customer.balance,Decimal('100'))

    def test_cash_custody_survives_actor_role_change(self):
        courier=User.objects.create_user(username='role-changing-courier',role='courier')
        payment=self.payment(method='cash',actor=courier)
        courier.role='cashier';courier.save(update_fields=['role'])
        self.assertEqual(self.post(f'payments/{payment.pk}/reverse',{'reason':'Wrong payment'}).status_code,200)
        self.assertEqual(sum(CashMovement.objects.filter(courier=courier).values_list('amount',flat=True)),Decimal('0'))
        self.assertFalse(CashboxMovement.objects.filter(cashier=courier).exists())

    def test_audit_recursively_removes_secret_fields(self):
        from .services import audit
        audit(self.admin,'client.updated',self.customer,{'meta':{'password':'SECRET_PASSWORD','children':[{'invitation_token':'SECRET_TOKEN','name':'Keep business name'}]},'reason':'Review'},before={'nested':{'access_token':'SECRET_ACCESS','balance':'0.00'}})
        event=AuditEvent.objects.get(action='client.updated')
        self.assertNotIn('SECRET',str([event.details,event.before,event.after]))
        self.assertEqual(event.details['meta']['children'][0]['name'],'Keep business name')

    def test_reversal_revises_only_unfunded_pending_refund(self):
        first=self.order(); second=self.order()
        original=self.payment(first);self.payment(second)
        for order in [first,second]:self.assertEqual(self.post(f'orders/{order.pk}/transition',{'status':'cancelled','version':1}).status_code,200)
        self.assertEqual(self.post(f'payments/{original.pk}/reverse',{'reason':'Receipt incorrect'}).status_code,200)
        removed=Refund.objects.get(order=first);kept=Refund.objects.get(order=second)
        self.assertEqual(removed.status,'cancelled')
        self.assertEqual(kept.status,'pending')
        self.assertEqual(kept.amount,Decimal('100'))
        self.assertEqual(self.post(f'refunds/{kept.pk}/confirm',{}).status_code,200)
        self.customer.refresh_from_db();self.assertEqual(self.customer.balance,Decimal('0'))

    def test_reversal_requires_reason_and_accounting_permission(self):
        payment=self.payment()
        self.assertEqual(self.post(f'payments/{payment.pk}/reverse',{}).status_code,422)
        self.api.force_authenticate(self.cashier)
        self.assertEqual(self.post(f'payments/{payment.pk}/reverse',{'reason':'No permission'}).status_code,403)
        payment.refresh_from_db();self.assertEqual(payment.status,'confirmed')

    def test_customer_can_only_read_their_own_refund_obligations(self):
        order=self.order();self.payment(order)
        self.post(f'orders/{order.pk}/transition',{'status':'cancelled','version':1})
        other=Client.objects.create(name='Other')
        Refund.objects.create(client=other,amount=300,method='kaspi',reason='Private')
        self.api.force_authenticate(self.user)
        response=self.api.get('/api/v1/refunds')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(len(response.json()['items']),1)
        self.assertEqual(response.json()['items'][0]['client_id'],str(self.customer.pk))

    def test_late_payment_increases_existing_pending_cancellation_refund(self):
        order=self.order();self.payment(order)
        self.post(f'orders/{order.pk}/transition',{'status':'cancelled','version':1})
        order.refresh_from_db();self.payment(order)
        refund=Refund.objects.get(order=order)
        self.assertEqual(refund.amount,Decimal('200'))
        self.assertEqual(refund.status,'pending')

    def test_late_payment_after_completed_refund_creates_only_new_obligation(self):
        order=self.order();self.payment(order)
        self.post(f'orders/{order.pk}/transition',{'status':'cancelled','version':1})
        original=Refund.objects.get(order=order)
        self.post(f'refunds/{original.pk}/confirm',{})
        order.refresh_from_db();self.payment(order)
        original.refresh_from_db();self.assertEqual(original.status,'confirmed')
        later=Refund.objects.get(order=order,status='pending')
        self.assertEqual(later.amount,Decimal('100'))
        self.assertNotEqual(later.pk,original.pk)
