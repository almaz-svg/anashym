import uuid
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from shop.models import Client,User,DeliveryPoint,Product,Batch,Quota

class Command(BaseCommand):
    help='Create repeatable local demo fixtures (never real payments)'
    def handle(self,*args,**options):
        today=timezone.localdate(); now=timezone.now()
        client,_=Client.objects.get_or_create(id=uuid.UUID('11111111-1111-4111-8111-111111111111'),defaults={'name':'Кофейня «Зелёный двор»','approval_status':'active','deferred_approved':True,'credit_limit':'50000.00','period_start':today})
        user,created=User.objects.get_or_create(username='+77010000001',defaults={'client':client,'first_name':'Алмаз'})
        if created: user.set_password('DemoClient2026!'); user.save()
        admin,created=User.objects.get_or_create(username='+77010000002',defaults={'role':'admin','is_staff':True,'is_superuser':True})
        if created: admin.set_password('DemoAdmin2026!'); admin.save()
        for phone,role in [('+77010000003','courier'),('+77010000004','cashier'),('+77010000005','accountant')]:
            staff,created=User.objects.get_or_create(username=phone,defaults={'role':role,'first_name':{'courier':'Курьер','cashier':'Кассир','accountant':'Бухгалтер'}[role]})
            if created: staff.set_password('DemoStaff2026!'); staff.save()
        DeliveryPoint.objects.get_or_create(id=uuid.UUID('22222222-2222-4222-8222-222222222222'),defaults={'client':client,'address':'Алматы, ул. Абая, 25','recipient':'Алмаз','phone':user.username})
        for index,(name,price) in enumerate([('Медовик','1500.00'),('Наполеон','1800.00'),('Чизкейк','2200.00')],1):
            product,_=Product.objects.get_or_create(id=uuid.UUID(f'33333333-3333-4333-8333-{index:012d}'),defaults={'name':name,'price':price,'description':'Свежий десерт ручной работы'})
            if not Batch.objects.filter(product=product).exists(): Batch.objects.create(product=product,manufactured_at=now-timedelta(hours=2),expires_at=now+timedelta(days=2),quantity=20)
            for days in [1,2,3]: Quota.objects.get_or_create(product=product,date=today+timedelta(days=days),defaults={'cutoff':now+timedelta(days=days,hours=-2),'quantity':50})
        self.stdout.write('Demo seeded. Client +77010000001 / DemoClient2026!; admin +77010000002 / DemoAdmin2026!')
