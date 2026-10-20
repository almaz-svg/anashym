import uuid
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Client, User, DeliveryPoint


class DeliveryPointSaveTests(TestCase):
    def test_formatted_phone_is_saved_in_international_format(self):
        client = Client.objects.create(name='Phone formats', approval_status='active')
        user = User.objects.create_user(username='address-phone', role='customer', client=client)
        api = APIClient()
        api.force_authenticate(user)
        for phone in ['8 (701) 999-98-81', '+7 701 999 98 81', '77019999881']:
            response = api.post('/api/v1/delivery-points', {
                'address': 'Алматы, Абая 25', 'recipient': 'Получатель', 'phone': phone
            }, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
            self.assertEqual(response.status_code, 201, response.content)
            self.assertEqual(response.json()['phone'], '+77019999881')

    def test_invalid_phone_explains_the_field_and_does_not_save(self):
        client = Client.objects.create(name='Invalid phone', approval_status='active')
        user = User.objects.create_user(username='address-invalid', role='customer', client=client)
        api = APIClient()
        api.force_authenticate(user)
        response = api.post('/api/v1/delivery-points', {
            'address': 'Алматы, Абая 25', 'recipient': 'Получатель', 'phone': 'wrong'
        }, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 422)
        self.assertIn('phone', response.json()['field_errors'])
        self.assertFalse(DeliveryPoint.objects.filter(client=client).exists())

    def test_address_survives_a_new_request_with_default_delivery_window(self):
        client = Client.objects.create(name='Address persistence', approval_status='active')
        user = User.objects.create_user(username='address-save', role='customer', client=client)
        api = APIClient()
        api.force_authenticate(user)
        response = api.post('/api/v1/delivery-points', {
            'address': 'Алматы, Абая 25', 'recipient': 'Получатель', 'phone': '+77019999881'
        }, format='json', HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(DeliveryPoint.objects.filter(client=client).count(), 1)
        fresh = APIClient()
        fresh.force_authenticate(user)
        items = fresh.get('/api/v1/delivery-points').json()['items']
        self.assertEqual(items[0]['id'], response.json()['id'])
        self.assertEqual(items[0]['address'], 'Алматы, Абая 25')
