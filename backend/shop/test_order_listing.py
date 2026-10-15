import json
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from decimal import Decimal
from .models import Client, DeliveryPoint, Order, Payment, User


class OrderListingTests(TestCase):
    def test_unpaid_page_queries_stay_bounded_and_cursor_reaches_history(self):
        customer=Client.objects.create(name='Paginated orders',approval_status='active')
        user=User.objects.create_user(username='+77016666662',client=customer)
        point=DeliveryPoint.objects.create(client=customer,address='QA',recipient='QA',phone=user.username)
        Order.objects.bulk_create([
            Order(client=customer,delivery_point=point,address_snapshot=json.dumps({'address':'QA'}),
                  kind='regular',status='submitted',total='1500',requested_delivery_at=timezone.now())
            for _ in range(24)
        ])
        self.client.force_login(user)
        with CaptureQueriesContext(connection) as one_queries:
            one=self.client.get('/api/v1/orders?limit=1')
        with CaptureQueriesContext(connection) as page_queries:
            first=self.client.get('/api/v1/orders?limit=20')
        self.assertEqual(one.status_code,200)
        self.assertEqual(first.status_code,200)
        self.assertLessEqual(len(page_queries),len(one_queries)+1)
        first=first.json()
        self.assertEqual(len(first['items']),20)
        second=self.client.get('/api/v1/orders',{'limit':20,'cursor':first['next_cursor']}).json()
        self.assertEqual(len(second['items']),4)
        self.assertIsNone(second['next_cursor'])
        ids=[row['id'] for row in first['items']+second['items']]
        self.assertEqual(len(set(ids)),24)
        self.assertTrue(all(row['payment_status']=='unpaid' for row in first['items']))

    def test_payment_list_attributes_remaining_advance_without_per_row_queries(self):
        customer=Client.objects.create(name='Payments',approval_status='active',balance='-2400')
        user=User.objects.create_user(username='+77016666663',client=customer)
        Payment.objects.bulk_create([
            Payment(client=customer,actor=user,method='kaspi',status='confirmed',
                    amount='100',confirmed_at=timezone.now())
            for _ in range(24)
        ])
        self.client.force_login(user)
        with CaptureQueriesContext(connection) as queries:
            response=self.client.get('/api/v1/payments?limit=100')
        self.assertEqual(response.status_code,200)
        self.assertLessEqual(len(queries),10)
        rows=response.json()['items']
        self.assertEqual(len(rows),24)
        self.assertEqual(sum((Decimal(row['unallocated_amount']) for row in rows),Decimal('0')),Decimal('2400'))
