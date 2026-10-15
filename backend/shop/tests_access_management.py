"""Access restoration and customer membership must not leak across organizations."""
import uuid
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.sessions.models import Session
from django.core import signing
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import AuditEvent, Client, DeliveryPoint, Order, User


class AccessManagementTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.admin = User.objects.create_user(username='access-admin', password='OldAdministrator123!', role='admin')
        self.company = Client.objects.create(name='First company', approval_status='active')
        self.other = Client.objects.create(name='Second company', approval_status='active')
        self.user = User.objects.create_user(username='+77019000001', password='OldCustomerPassword123!', client=self.company)
        self.api.force_authenticate(self.admin)

    def post(self, path, data=None):
        return self.api.post('/api/v1/' + path, data or {}, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))

    def reset(self):
        response = self.post(f'staff/{self.user.pk}/reset-access')
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()['invitation_token']

    def test_reset_revokes_old_password_sessions_and_requires_one_time_change(self):
        customer_api = APIClient()
        self.assertTrue(customer_api.login(username=self.user.username, password='OldCustomerPassword123!'))
        session_key = customer_api.session.session_key
        token = self.reset()
        self.user.refresh_from_db()
        self.assertTrue(self.user.must_change_password)
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(Session.objects.filter(session_key=session_key).exists())
        reset_event = AuditEvent.objects.get(action='account.access_reset')
        self.assertFalse(reset_event.before['must_change_password'])
        self.assertTrue(reset_event.after['must_change_password'])
        self.assertNotIn('password', reset_event.before)
        self.assertNotIn('password', reset_event.after)
        self.assertNotIn(token, str(list(AuditEvent.objects.values('details', 'before', 'after'))))
        self.api.force_authenticate(None)
        changed = self.post('auth/change-password', {'token': token, 'password': 'NewCustomerPassword123!'})
        self.assertEqual(changed.status_code, 200, changed.content)
        self.user.refresh_from_db()
        self.assertFalse(self.user.must_change_password)
        self.assertTrue(self.user.check_password('NewCustomerPassword123!'))
        self.assertEqual(self.post('auth/change-password', {'token': token, 'password': 'AnotherPassword123!'}).status_code, 422)

    def test_new_reset_invalidates_earlier_link_and_expired_link_is_rejected(self):
        first = self.reset()
        second = self.reset()
        self.api.force_authenticate(None)
        self.assertEqual(self.post('auth/change-password', {'token': first, 'password': 'NewPassword12345!'}).status_code, 422)
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 86401):
            self.assertEqual(self.post('auth/change-password', {'token': second, 'password': 'NewPassword12345!'}).status_code, 422)

    def test_reset_and_membership_mutation_are_admin_only(self):
        self.api.force_authenticate(self.user)
        self.assertEqual(self.post(f'staff/{self.admin.pk}/reset-access').status_code, 403)
        self.assertEqual(self.post(f'clients/{self.other.pk}/members', {'phone': '+77019000002', 'name': 'Intruder'}).status_code, 403)
        self.assertEqual(self.api.get(f'/api/v1/clients/{self.other.pk}/members').status_code, 403)

    def test_invited_member_uses_existing_company_and_can_only_see_its_orders(self):
        for company in (self.company, self.other):
            point = DeliveryPoint.objects.create(client=company, address='Address', recipient='Name', phone='+77019000003')
            Order.objects.create(client=company, delivery_point=point, address_snapshot='{}', kind='regular', total=100, requested_delivery_at=timezone.now())
        response = self.post(f'clients/{self.company.pk}/members', {'phone': '+77019000002', 'name': 'Colleague'})
        self.assertEqual(response.status_code, 201, response.content)
        member = User.objects.get(username='+77019000002')
        self.assertEqual(member.client_id, self.company.pk)
        self.assertEqual(Client.objects.count(), 2)
        self.assertEqual(member.role, 'customer')
        self.api.force_authenticate(None)
        accepted = self.post('auth/activate', {'token': response.json()['invitation_token'], 'password': 'ColleaguePassword123!'})
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(self.post('auth/activate', {'token': response.json()['invitation_token'], 'password': 'ColleaguePassword123!'}).status_code, 422)
        self.api.force_authenticate(User.objects.get(pk=member.pk))
        rows = self.api.get('/api/v1/orders').json()['items']
        self.assertEqual([row['client_id'] for row in rows], [str(self.company.pk)])

    def test_forced_change_restricts_business_but_allows_password_and_identity(self):
        self.user.must_change_password = True
        self.user.save(update_fields=['must_change_password'])
        self.api.force_authenticate(self.user)
        identity = self.api.get('/api/v1/auth/me')
        self.assertTrue(identity.json()['must_change_password'])
        blocked = self.api.get('/api/v1/orders')
        self.assertEqual(blocked.status_code, 403)
        self.assertEqual(blocked.json()['code'], 'PASSWORD_CHANGE_REQUIRED')
        bad = self.post('auth/change-password', {'current_password': 'wrong-password', 'password': 'NewPassword12345!'})
        self.assertEqual(bad.status_code, 422)
        self.assertIn('current_password', bad.json()['field_errors'])
        good = self.post('auth/change-password', {'current_password': 'OldCustomerPassword123!', 'password': 'NewPassword12345!'})
        self.assertEqual(good.status_code, 200, good.content)

    def test_existing_other_company_account_cannot_be_reassigned(self):
        self.user.client = self.other
        self.user.save(update_fields=['client'])
        result = self.post(f'clients/{self.company.pk}/members', {'phone': self.user.username, 'name': 'Transfer'})
        self.assertEqual(result.status_code, 409)
        self.user.refresh_from_db()
        self.assertEqual(self.user.client_id, self.other.pk)

    def test_archive_preserves_company_and_members_and_can_be_restored(self):
        response = self.post(f'clients/{self.company.pk}/archive')
        self.assertEqual(response.status_code, 200, response.content)
        self.company.refresh_from_db()
        self.assertTrue(self.company.archived)
        event = AuditEvent.objects.get(action='client.archived')
        self.assertFalse(event.before['archived'])
        self.assertTrue(event.after['archived'])
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(self.post(f'clients/{self.company.pk}/members', {'phone': '+77019000004', 'name': 'New'}).status_code, 409)
        self.assertEqual(self.post(f'clients/{self.company.pk}/restore').status_code, 200)
        self.company.refresh_from_db()
        self.assertFalse(self.company.archived)

    def test_legacy_staff_invitation_stays_usable(self):
        staff = User.objects.create_user(username='+77019000005', role='cashier')
        token = signing.dumps({'staff': str(staff.pk), 'stamp': staff.password}, salt='staff-invite')
        self.api.force_authenticate(None)
        result = self.post('auth/activate', {'token': token, 'password': 'NewCashierPassword123!'})
        self.assertEqual(result.status_code, 200, result.content)

    def test_members_are_paginated_with_organization_scoped_cursors(self):
        for number in range(3):
            User.objects.create_user(username=f'+7701900010{number}', client=self.company)
        response = self.api.get(f'/api/v1/clients/{self.company.pk}/members', {'limit': 2})
        self.assertEqual(response.status_code, 200, response.content)
        first = response.json()
        self.assertEqual(len(first['items']), 2)
        self.assertTrue(first['next_cursor'])
        second = self.api.get(f'/api/v1/clients/{self.company.pk}/members', {'limit': 2, 'cursor': first['next_cursor']}).json()
        self.assertEqual(len(second['items']), 2)
        self.assertFalse(set(row['id'] for row in first['items']) & set(row['id'] for row in second['items']))
        self.assertEqual(self.api.get(f'/api/v1/clients/{self.other.pk}/members', {'cursor': first['next_cursor']}).status_code, 422)


class CourierPhotoPolicyTests(SimpleTestCase):
    def test_assigned_courier_can_read_delivered_history_and_attach_returns_only(self):
        from .photos import _allowed
        courier_id = uuid.uuid4()
        courier = SimpleNamespace(id=courier_id, role='courier')
        order = SimpleNamespace(courier_id=courier_id, status='delivered', cash_collection_assigned=False)
        self.assertTrue(_allowed(courier, order, 'delivery'))
        self.assertFalse(_allowed(courier, order, 'payment'))
        self.assertTrue(_allowed(courier, order, 'return', writing=True))
        self.assertTrue(_allowed(courier, order, 'exchange', writing=True))
        self.assertFalse(_allowed(courier, order, 'delivery', writing=True))
        self.assertFalse(_allowed(courier, order, 'cash', writing=True))
        order.courier_id = uuid.uuid4()
        self.assertFalse(_allowed(courier, order, 'delivery'))
        self.assertFalse(_allowed(courier, order, 'return', writing=True))
