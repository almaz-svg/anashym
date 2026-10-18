"""Action-level role and ownership regressions; no external services required."""
import uuid
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from .models import (CashMovement, CashboxMovement, Client, DeliveryPoint, Handover,
                     LedgerEntry, Notification, Payment, Product, Refund, User)


class RoleActionAuditTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.company = Client.objects.create(name='Audit company', approval_status='active')
        self.other_company = Client.objects.create(name='Other company', approval_status='active')
        self.users = {role: User.objects.create_user(username='audit-' + role, role=role,
                      client=self.company if role == 'customer' else None)
                      for role in ['admin', 'customer', 'courier', 'cashier', 'accountant']}
        self.other_courier = User.objects.create_user(username='audit-other-courier', role='courier')

    def post(self, role, path, data):
        self.api.force_authenticate(self.users[role])
        return self.api.post('/api/v1/' + path, data, format='json',
                             HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def test_product_creation_requires_admin_and_rejected_roles_leave_no_product(self):
        payload = {'name': 'Audit cake', 'price_amount': '1200', 'preparation_minutes': 30}
        for role in ['customer', 'courier', 'cashier', 'accountant']:
            with self.subTest(role=role):
                result = self.post(role, 'products', payload)
                self.assertEqual(result.status_code, 403, result.content)
                self.assertFalse(Product.objects.exists())
        self.assertEqual(self.post('admin', 'products', payload).status_code, 201)
        self.assertEqual(Product.objects.count(), 1)

    def test_approval_requires_admin_and_does_not_change_company_on_denial(self):
        self.company.approval_status = 'pending'
        self.company.save()
        for role in ['courier', 'cashier', 'accountant']:
            result = self.post(role, f'clients/{self.company.pk}/approve', {'approval_status': 'active'})
            self.assertEqual(result.status_code, 403, result.content)
            self.company.refresh_from_db()
            self.assertEqual(self.company.approval_status, 'pending')
        self.assertEqual(self.post('admin', f'clients/{self.company.pk}/approve',
                                   {'approval_status': 'active'}).status_code, 200)

    def test_accountant_can_close_periods_but_cannot_operate_cash(self):
        self.assertEqual(self.post('accountant', 'periods/close', {}).status_code, 200)
        for path, payload in [('shifts', {'action': 'open'}),
                              ('cash-movements', {'courier_id': str(self.users['courier'].pk),
                               'amount': '100', 'direction': 'issue', 'reason': 'Float'}),
                              ('handovers', {'amount': '100'})]:
            with self.subTest(path=path):
                result = self.post('accountant', path, payload)
                self.assertEqual(result.status_code, 403, result.content)
        self.assertFalse(CashMovement.objects.exists())

    def test_cashier_issue_courier_handover_cashier_confirm_preserves_client_ledger(self):
        result = self.post('cashier', 'cash-movements', {'courier_id': str(self.users['courier'].pk),
                           'amount': '500', 'direction': 'issue', 'reason': 'Change float'})
        self.assertEqual(result.status_code, 201, result.content)
        result = self.post('courier', 'handovers', {'amount': '300'})
        self.assertEqual(result.status_code, 201, result.content)
        path = 'handovers/' + result.json()['id'] + '/confirm'
        for role in ['customer', 'courier', 'accountant']:
            self.assertEqual(self.post(role, path, {'amount': '300'}).status_code, 403)
        result = self.post('cashier', path, {'amount': '300'})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(sum(CashMovement.objects.values_list('amount', flat=True)), Decimal('200'))
        self.assertFalse(Payment.objects.exists())
        self.assertFalse(LedgerEntry.objects.exists())

    def test_courier_cash_scope_ignores_other_courier_filter(self):
        CashMovement.objects.create(courier=self.users['courier'], actor=self.users['cashier'], amount=100, kind='issue')
        CashMovement.objects.create(courier=self.other_courier, actor=self.users['cashier'], amount=900, kind='issue')
        self.api.force_authenticate(self.users['courier'])
        result = self.api.get('/api/v1/cash', {'courier_id': str(self.other_courier.pk)})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(Decimal(result.json()['cash_amount']), Decimal('100'))
        result = self.api.get('/api/v1/cash-movements')
        self.assertEqual(len(result.json()['items']), 1)
        self.assertEqual(result.json()['items'][0]['courier_id'], str(self.users['courier'].pk))

    def test_customer_financial_lists_do_not_leak_other_company(self):
        for company in [self.company, self.other_company]:
            Payment.objects.create(client=company, actor=self.users['cashier'], method='kaspi', amount=100)
            LedgerEntry.objects.create(client=company, actor=self.users['cashier'], kind='delivery', amount=100, reference=str(uuid.uuid4()))
            Refund.objects.create(client=company, amount=10, method='kaspi', reason='Audit')
        self.api.force_authenticate(self.users['customer'])
        for route in ['payments', 'ledger', 'refunds']:
            with self.subTest(route=route):
                result = self.api.get('/api/v1/' + route)
                self.assertEqual(result.status_code, 200, result.content)
                self.assertEqual(len(result.json()['items']), 1)
                self.assertEqual(result.json()['items'][0]['client_id'], str(self.company.pk))

    def test_customer_and_courier_cannot_confirm_payments(self):
        payment = Payment.objects.create(client=self.company, actor=self.users['cashier'],
                                         method='kaspi', amount=100, reference='audit-payment')
        for role in ['customer', 'courier']:
            result = self.post(role, f'payments/{payment.pk}/confirm', {})
            self.assertEqual(result.status_code, 403, result.content)
            payment.refresh_from_db()
            self.assertEqual(payment.status, 'pending')
        self.assertFalse(LedgerEntry.objects.exists())
        result = self.post('accountant', f'payments/{payment.pk}/confirm', {})
        self.assertEqual(result.status_code, 200, result.content)
        self.assertEqual(LedgerEntry.objects.get().amount, Decimal('-100'))

    def test_cashier_cannot_reverse_payment_accountant_can(self):
        payment = Payment.objects.create(client=self.company, actor=self.users['cashier'],
                                         method='kaspi', amount=100, reference='audit-reverse')
        self.assertEqual(self.post('cashier', f'payments/{payment.pk}/confirm', {}).status_code, 200)
        path = f'payments/{payment.pk}/reverse'
        self.assertEqual(self.post('cashier', path, {'reason': 'Correction'}).status_code, 403)
        self.assertEqual(self.post('accountant', path, {'reason': 'Correction'}).status_code, 200)
        self.assertEqual(sum(LedgerEntry.objects.values_list('amount', flat=True)), Decimal('0'))

    def test_notifications_only_show_current_user_and_cannot_change_others(self):
        own = Notification.objects.create(user=self.users['customer'], message='Own', object_id='1')
        other = Notification.objects.create(user=self.users['admin'], message='Private', object_id='2')
        self.api.force_authenticate(self.users['customer'])
        self.assertEqual([row['id'] for row in self.api.get('/api/v1/notifications').json()['items']], [own.pk])
        self.post('customer', f'notifications/{other.pk}/read', {})
        other.refresh_from_db()
        self.assertFalse(other.read)
        self.assertEqual(self.post('customer', f'notifications/{own.pk}/read', {}).status_code, 200)
        own.refresh_from_db()
        self.assertTrue(own.read)

    def test_audit_read_access_is_admin_accountant_only(self):
        for role in self.users:
            self.api.force_authenticate(self.users[role])
            result = self.api.get('/api/v1/audit')
            self.assertEqual(result.status_code, 200 if role in ['admin', 'accountant'] else 403)

    def test_customer_delivery_points_only_include_confirmed_own_points(self):
        visible = DeliveryPoint.objects.create(client=self.company, address='Visible',
                    recipient='Customer', phone='+77000000001', confirmed=True)
        DeliveryPoint.objects.create(client=self.company, address='Pending',
                    recipient='Customer', phone='+77000000001', confirmed=False)
        DeliveryPoint.objects.create(client=self.other_company, address='Other',
                    recipient='Other', phone='+77000000002', confirmed=True)
        self.api.force_authenticate(self.users['customer'])
        response = self.api.get('/api/v1/delivery-points')
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row['id'] for row in response.json()['items']], [str(visible.pk)])
        response = self.api.get('/api/v1/delivery-points', {'client_id': str(self.other_company.pk)})
        self.assertEqual(response.json()['items'], [])
        self.api.force_authenticate(self.users['admin'])
        self.assertEqual(len(self.api.get('/api/v1/delivery-points').json()['items']), 3)

    def test_get_cannot_confirm_handover_or_move_money(self):
        CashMovement.objects.create(courier=self.users['courier'], actor=self.users['cashier'], amount=100, kind='issue')
        handover = Handover.objects.create(courier=self.users['courier'], amount=100)
        self.api.force_authenticate(self.users['cashier'])
        result = self.api.get(f'/api/v1/handovers/{handover.pk}/confirm')
        handover.refresh_from_db()
        self.assertEqual(handover.status, 'pending', f'GET {result.status_code} changed handover state')
        self.assertFalse(CashboxMovement.objects.exists())

    def test_get_and_head_cannot_invoke_business_actions(self):
        self.api.force_authenticate(self.users['admin'])
        actions = {
            'orders': ['transition', 'delivery', 'delivery-failed', 'payment-mode',
                       'goods-return', 'fulfill', 'reschedule', 'reschedule-confirm',
                       'assign-collection', 'unexpected-suffix'],
            'payments': ['confirm', 'reject', 'reverse'],
            'handovers': ['confirm', 'reject'], 'returns': ['receive', 'decide'],
            'refunds': ['confirm'], 'notifications': ['read'], 'batches': ['adjust'],
            'products': ['update', 'archive', 'restore'], 'stock-movements': ['resolve'],
            'staff': ['role', 'reset-access'], 'clients': ['approve', 'archive', 'restore'],
        }
        paths = ['periods/close', 'ai/order-draft', 'auth/logout', 'auth/login',
                 'auth/register', 'auth/activate', 'auth/change-password', 'auth/accept-invitation']
        for resource, names in actions.items():
            paths.extend(f'{resource}/{uuid.uuid4()}/{action}' for action in names)
        for path in paths:
            for method in ['get', 'head']:
                with self.subTest(path=path, method=method):
                    result = getattr(self.api, method)('/api/v1/' + path)
                    self.assertEqual(result.status_code, 405, result.content)

    def test_session_post_still_requires_csrf_and_idempotency(self):
        api = APIClient(enforce_csrf_checks=True)
        api.force_login(self.users['cashier'])
        handover = Handover.objects.create(courier=self.users['courier'], amount=100)
        path = f'/api/v1/handovers/{handover.pk}/confirm'
        self.assertEqual(api.get(path).status_code, 405)
        self.assertEqual(api.post(path, {'amount': '100'}, format='json',
                                  HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4())).status_code, 403)
        api.get('/api/v1/auth/csrf')
        result = api.post(path, {'amount': '100'}, format='json',
                          HTTP_X_CSRFTOKEN=api.cookies['csrftoken'].value)
        self.assertEqual(result.status_code, 422, result.content)
        handover.refresh_from_db()
        self.assertEqual(handover.status, 'pending')

    def test_get_cannot_confirm_refund_or_create_ledger_entry(self):
        payment = Payment.objects.create(client=self.company, actor=self.users['cashier'],
                                         method='kaspi', amount=100, reference='audit-refund')
        self.assertEqual(self.post('cashier', f'payments/{payment.pk}/confirm', {}).status_code, 200)
        result = self.post('cashier', 'refunds', {'client_id': str(self.company.pk),
                           'amount': '100', 'method': 'kaspi', 'reason': 'Refund advance'})
        self.assertEqual(result.status_code, 201, result.content)
        refund = Refund.objects.get(pk=result.json()['id'])
        count = LedgerEntry.objects.count()
        result = self.api.get(f'/api/v1/refunds/{refund.pk}/confirm')
        refund.refresh_from_db()
        self.assertEqual(refund.status, 'pending', f'GET {result.status_code} changed refund state')
        self.assertEqual(LedgerEntry.objects.count(), count)
