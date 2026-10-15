import json
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from .models import Client,User,DeliveryPoint,Order,LedgerEntry,Payment,PaymentAllocation
from .views import order_data


class OrderBalancePresentationTests(TestCase):
    def test_paid_order_after_return_has_zero_outstanding(self):
        client=Client.objects.create(name='Net order amount',approval_status='active')
        actor=User.objects.create_user(username='+77016666661',password='LocalTestsOnly!',client=client)
        point=DeliveryPoint.objects.create(client=client,address='QA',recipient='QA',phone=actor.username)
        order=Order.objects.create(client=client,delivery_point=point,address_snapshot=json.dumps({'address':'QA'}),
            kind='regular',status='delivered',total='15000.00',delivered_total='15000.00',requested_delivery_at=timezone.now())
        LedgerEntry.objects.create(client=client,order=order,actor=actor,kind='return',amount='-1500.00',reference='order-net-return')
        payment=Payment.objects.create(client=client,order=order,actor=actor,method='kaspi',status='confirmed',amount='13500.00')
        PaymentAllocation.objects.create(payment=payment,order=order,amount='13500.00')
        order.refresh_from_db()
        result=order_data(order)
        self.assertEqual(Decimal(result['outstanding_amount']),Decimal('0.00'))
        self.assertEqual(result['payment_status'],'paid')
