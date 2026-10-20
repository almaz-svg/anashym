from django.test import TestCase
from rest_framework.test import APIClient
from .models import Client, Notification, User


class RegistrationQueueTests(TestCase):
    def test_registration_is_active_visible_and_notifies_only_admins(self):
        admin = User.objects.create_user(username='queue-admin', role='admin')
        other_admin = User.objects.create_user(username='queue-admin-2', role='admin')
        User.objects.create_user(username='queue-courier', role='courier')
        api = APIClient()
        body = {'phone': '+77019999881', 'password': 'TestOnlyPassword123!',
                'name': 'New coffee shop', 'category': 'coffee_shop', 'description': 'Coffee shop',
                'expected_order_quantity': 10, 'expected_order_frequency': 'weekly'}
        response = api.post('/api/v1/auth/register', body, format='json')
        self.assertEqual(response.status_code, 201, response.content)
        client = Client.objects.get(name=body['name'])
        self.assertEqual(client.approval_status, 'active')
        api.force_authenticate(admin)
        listing = api.get('/api/v1/clients').json()
        self.assertIn(str(client.pk), [item['id'] for item in listing['items']])
        notices = Notification.objects.filter(message='client.registration_requested', object_id=str(client.pk))
        self.assertSetEqual(set(notices.values_list('user_id', flat=True)), {admin.pk, other_admin.pk})
        self.assertNotIn(body['password'], str(list(notices.values())))
        repeated = APIClient().post('/api/v1/auth/register', body, format='json')
        self.assertEqual(repeated.status_code, 422)
        self.assertEqual(notices.count(), 2)
