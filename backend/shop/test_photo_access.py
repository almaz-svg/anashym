import io
import tempfile
import uuid
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from PIL import Image
from .models import Client, Order, DeliveryPoint, User, Photo


class PrivatePhotoAccessTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.setting = override_settings(MEDIA_ROOT=self.media.name)
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        self.addCleanup(self.media.cleanup)
        call_command('seed_demo',verbosity=0)
        self.customer = User.objects.get(username='+77010000001')
        self.courier = User.objects.get(username='+77010000003')
        self.client2 = Client.objects.create(name='Other photo client',approval_status='active')
        self.other = User.objects.create_user(username='+77010000991',password='PhotoTestsOnly!',client=self.client2)
        self.order = Order.objects.create(client=self.customer.client,delivery_point=DeliveryPoint.objects.filter(client=self.customer.client).first(),
            address_snapshot='private address',kind='regular',total='1500.00',requested_delivery_at=timezone.now(),courier=self.courier,status='out_for_delivery')
        self.api = APIClient()

    def upload(self,purpose='payment',key=None,content=None):
        if content is None:
            stream = io.BytesIO()
            Image.new('RGB',(12,12),'green').save(stream,format='PNG')
            content=stream.getvalue()
        return self.api.post('/api/v1/files',{'order_id':str(self.order.pk),'purpose':purpose,
            'files':SimpleUploadedFile('proof.png',content,content_type='image/png')},format='multipart',HTTP_IDEMPOTENCY_KEY=key or str(uuid.uuid4()))

    def test_private_photo_scope_and_same_key_replay(self):
        self.api.force_login(self.customer)
        key=str(uuid.uuid4())
        first=self.upload(key=key)
        self.assertEqual(first.status_code,201,first.content)
        repeated=self.upload(key=key)
        self.assertEqual(repeated.json(),first.json())
        self.assertEqual(Photo.objects.filter(order=self.order).count(),1)
        pid=first.json()['items'][0]['id']
        info=self.api.get('/api/v1/files/'+pid)
        self.assertEqual(info.status_code,200)
        url=info.json()['url']
        valid=self.api.get(url)
        self.assertEqual(valid.status_code,200)
        self.assertTrue(b''.join(valid.streaming_content))
        self.assertEqual(self.api.get('/api/v1/files/'+pid+'/content?token=bad').status_code,403)
        self.api.force_login(self.other)
        self.assertEqual(self.api.get('/api/v1/files/'+pid).status_code,404)
        self.assertEqual(self.api.get(url).status_code,404)

    def test_completed_courier_can_read_own_history_and_attach_return_photos(self):
        self.api.force_login(self.courier)
        first=self.upload('delivery')
        self.assertEqual(first.status_code,201,first.content)
        pid=first.json()['items'][0]['id']
        Order.objects.filter(pk=self.order.pk).update(status='delivered')
        self.assertEqual(self.api.get('/api/v1/files/'+pid).status_code,200)
        self.assertEqual(self.upload('cash').status_code,404)
        self.assertEqual(self.upload('delivery').status_code,404)
        self.assertEqual(self.upload('return').status_code,201)
        self.assertEqual(self.upload('exchange').status_code,201)
        other_courier = User.objects.create_user(username='+77010000992', role='courier')
        self.api.force_login(other_courier)
        self.assertEqual(self.api.get('/api/v1/files/'+pid).status_code,404)
        self.assertEqual(self.upload('return').status_code,404)

    def test_invalid_image_does_not_create_attachment(self):
        self.api.force_login(self.customer)
        response=self.upload(content=b'fake photo')
        self.assertEqual(response.status_code,422,response.content)
        self.assertFalse(Photo.objects.filter(order=self.order).exists())

    def test_six_files_return_structured_validation_error(self):
        self.api.force_login(self.customer)
        response=self.api.post('/api/v1/files',{'order_id':str(self.order.pk),'purpose':'payment',
            'files':[SimpleUploadedFile(f'{i}.png',b'placeholder',content_type='image/png') for i in range(6)]},
            format='multipart',HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()))
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.json()['code'],'VALIDATION_ERROR')
        self.assertIn('files',response.json()['field_errors'])
