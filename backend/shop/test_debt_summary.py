from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Client, DeliveryPoint, Order, User, Payment, PaymentAllocation, LedgerEntry, Refund


class DebtSummaryTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name='First', approval_status='active', balance='2500.00')
        Client.objects.create(name='Other debtor', approval_status='active', balance='4000.00')
        Client.objects.create(name='Advance', approval_status='active', balance='-9000.00')
        self.customer = User.objects.create_user(username='debt-customer', client=self.client_org)
        self.admin = User.objects.create_user(username='debt-admin', role='admin')
        self.api = APIClient()

    def summary(self, user):
        self.api.force_authenticate(user)
        response = self.api.get('/api/v1/debt-summary')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_customer_sees_only_own_debt_and_advance_does_not_cancel_other_clients_debt(self):
        self.assertEqual(self.summary(self.customer)['debt_amount'], '2500.00')
        self.assertEqual(self.summary(self.admin)['debt_amount'], '6500.00')
        self.client_org.balance = -100
        self.client_org.save()
        self.assertEqual(self.summary(self.customer)['debt_amount'], '0.00')

    def test_courier_sees_only_unpaid_deliveries_assigned_to_them(self):
        courier = User.objects.create_user(username='debt-courier', role='courier')
        point = DeliveryPoint.objects.create(client=self.client_org, address='QA', recipient='QA', phone='+77010000001')
        def order(assigned):
            return Order.objects.create(client=self.client_org, delivery_point=point, courier=assigned,
                total=1000, delivered_total=1000, status='delivered', address_snapshot='{}',
                requested_delivery_at=timezone.now())
        own = order(courier)
        order(None)
        payment = Payment.objects.create(client=self.client_org, order=own, actor=self.admin,
            method='kaspi', amount=200, status='confirmed')
        PaymentAllocation.objects.create(payment=payment, order=own, amount=200)
        LedgerEntry.objects.create(client=self.client_org, order=own, actor=self.admin, kind='return', amount=-100, reference='summary-return')
        self.assertEqual(self.summary(courier)['debt_amount'], '700.00')

    def test_pending_customer_can_read_own_debt_but_anonymous_cannot(self):
        self.assertEqual(self.api.get('/api/v1/debt-summary').status_code, 401)
        self.client_org.approval_status = 'pending'
        self.client_org.save()
        self.api.force_authenticate(self.customer)
        self.assertEqual(self.api.get('/api/v1/debt-summary').status_code, 200)

    def test_staff_total_includes_reserved_refunds_without_querying_each_client(self):
        from .debt_summary import debt_summary
        Refund.objects.create(client=self.client_org, amount=500, method='kaspi', reason='QA')
        for i in range(8):
            Client.objects.create(name=f'Zero {i}', approval_status='active')
        with self.assertNumQueries(2):
            result = debt_summary(self.admin)
        self.assertEqual(result['debt_amount'], '7000.00')
