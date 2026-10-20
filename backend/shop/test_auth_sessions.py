"""Registration and all account roles use actual session cookies and CSRF."""
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
import io


class AuthSessionTests(TestCase):
    def setUp(self):
        call_command('seed_demo', stdout=io.StringIO())

    def csrf(self, api):
        self.assertEqual(api.get('/api/v1/auth/csrf').status_code, 204)
        return {'HTTP_X_CSRFTOKEN': api.cookies['csrftoken'].value}

    def test_every_demo_role_can_sign_in_persist_session_and_sign_out(self):
        for phone, password, role in [
            ('+77010000001', 'DemoClient2026!', 'customer'),
            ('+77010000002', 'DemoAdmin2026!', 'admin'),
            ('+77010000003', 'DemoStaff2026!', 'courier'),
            ('+77010000004', 'DemoStaff2026!', 'cashier'),
            ('+77010000005', 'DemoStaff2026!', 'accountant'),
        ]:
            with self.subTest(role=role):
                api = APIClient(enforce_csrf_checks=True)
                response = api.post('/api/v1/auth/login', {'phone': phone, 'password': password},
                                    format='json', **self.csrf(api))
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()['role'], role)
                self.assertEqual(api.get('/api/v1/auth/me').json()['role'], role)
                self.assertEqual(api.post('/api/v1/auth/logout', {}, format='json', **self.csrf(api)).status_code, 204)
                self.assertEqual(api.get('/api/v1/auth/me').status_code, 401)

    def test_registered_customer_can_sign_in_with_immediate_access(self):
        api = APIClient(enforce_csrf_checks=True)
        account = {'phone': '+77010000999', 'password': 'RegistrationTest2026!',
                   'name': 'Registration test', 'category': 'individual',
                   'description': 'Test account', 'expected_order_quantity': 1,
                   'expected_order_frequency': 'weekly'}
        response = api.post('/api/v1/auth/register', account, format='json', **self.csrf(api))
        self.assertEqual(response.status_code, 201, response.content)
        response = api.post('/api/v1/auth/login', {key: account[key] for key in ('phone', 'password')},
                            format='json', **self.csrf(api))
        self.assertEqual(response.status_code, 200, response.content)
        current = api.get('/api/v1/auth/me').json()
        self.assertEqual(current['approval_status'], 'active')
        self.assertEqual(current['role'], 'customer')
