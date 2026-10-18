import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from .models import User


class StaffUsernameTests(TestCase):
    def test_staff_invitation_activation_and_login_accept_named_usernames(self):
        admin = User.objects.create_user(username='existing-admin', role='admin')
        api = APIClient()
        for username, role in [('almazalmaz', 'admin'), ('dollar', 'cashier'), ('книга', 'courier')]:
            api.force_authenticate(admin)
            response = api.post('/api/v1/staff', {'phone': username, 'name': 'Staff', 'role': role},
                format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(response.status_code, 201, response.content)
            user = User.objects.get(username=username)
            self.assertFalse(user.has_usable_password())
            api.force_authenticate(None)
            password = 'TestOnlyPassword123!'
            activation = api.post('/api/v1/auth/activate', {
                'token': response.json()['invitation_token'], 'password': password}, format='json')
            self.assertEqual(activation.status_code, 200, activation.content)
            signed_in = api.post('/api/v1/auth/login', {'phone': username, 'password': password}, format='json')
            self.assertEqual(signed_in.status_code, 200, signed_in.content)
            self.assertEqual(signed_in.json()['role'], role)

    def test_invalid_staff_username_is_rejected(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_user(username='admin', role='admin'))
        for username in ['has spaces', '../path', 'x' * 151, '', 123]:
            response = api.post('/api/v1/staff', {'phone': username, 'name': 'Staff', 'role': 'courier'},
                format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(response.status_code, 422)
