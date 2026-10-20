import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models import Q,F
from django.core.exceptions import ValidationError

class Client(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=200)
    category=models.CharField(max_length=30,default='coffee_shop')
    category_other=models.CharField(max_length=200,blank=True)
    description=models.TextField(blank=True)
    expected_order_quantity=models.PositiveIntegerField(default=1)
    expected_order_frequency=models.CharField(max_length=200,blank=True)
    approval_status=models.CharField(max_length=20,default='pending',choices=[('pending','Ожидает'),('active','Одобрен'),('rejected','Отклонён')])
    archived=models.BooleanField(default=False)
    deferred_approved=models.BooleanField(default=False)
    credit_limit=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    reserved_credit=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    balance=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    overdue=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    period_days=models.PositiveIntegerField(default=14,choices=[(7,'7 дней'),(14,'14 дней'),(30,'30 дней')])
    period_start=models.DateField(default='2026-10-13')
    preferred_payment_mode=models.CharField(max_length=20,default='deferred')
    requested_period_days=models.PositiveIntegerField(default=14)
    pending_period_days=models.PositiveIntegerField(null=True)
    period_change_at=models.DateField(null=True)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(reserved_credit__gte=0),name='credit_reserve_nonnegative'),models.CheckConstraint(condition=Q(credit_limit__gte=0),name='credit_limit_nonnegative'),models.CheckConstraint(condition=Q(period_days__in=[7,14,30]),name='client_valid_period')]

class User(AbstractUser):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    role=models.CharField(max_length=20,default='customer')
    client=models.ForeignKey(Client,null=True,blank=True,on_delete=models.PROTECT)
    must_change_password=models.BooleanField(default=False)

class DeliveryPoint(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    address=models.CharField(max_length=300)
    recipient=models.CharField(max_length=150)
    phone=models.CharField(max_length=20)
    confirmed=models.BooleanField(default=True)
    window_start=models.TimeField(default='09:00')
    window_end=models.TimeField(default='20:00')

    def clean(self):
        super().clean()
        try:
            start=self._meta.get_field('window_start').to_python(self.window_start)
            end=self._meta.get_field('window_end').to_python(self.window_end)
        except ValidationError:
            return  # full_clean reports malformed values on their own fields.
        if start is not None and end is not None and start>=end:
            raise ValidationError({
                'window_start':['Начало доставки должно быть раньше окончания.'],
                'window_end':['Окончание доставки должно быть позже начала в тот же день.'],
            })

class Product(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    name=models.CharField(max_length=150)
    description=models.TextField(blank=True)
    image_url=models.URLField(max_length=500,blank=True)
    shelf_life_hours=models.PositiveIntegerField(default=72)
    price=models.DecimalField(max_digits=18,decimal_places=2)
    preparation_minutes=models.PositiveIntegerField(default=60)
    active=models.BooleanField(default=True)

class Batch(models.Model):
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    manufactured_at=models.DateTimeField()
    expires_at=models.DateTimeField()
    quantity=models.PositiveIntegerField()
    reserved=models.PositiveIntegerField(default=0)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(reserved__lte=F('quantity')),name='batch_reserve_within_stock')]

class Quota(models.Model):
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    date=models.DateField()
    cutoff=models.DateTimeField()
    quantity=models.PositiveIntegerField()
    reserved=models.PositiveIntegerField(default=0)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['product','date'],name='unique_quota'),models.CheckConstraint(condition=Q(reserved__lte=F('quantity')),name='quota_reserve_within_capacity')]

class Order(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    delivery_point=models.ForeignKey(DeliveryPoint,on_delete=models.PROTECT)
    address_snapshot=models.TextField()
    kind=models.CharField(max_length=20)
    status=models.CharField(max_length=30,default='submitted')
    payment_mode=models.CharField(max_length=20,default='deferred')
    total=models.DecimalField(max_digits=18,decimal_places=2)
    created_at=models.DateTimeField(auto_now_add=True)
    requested_delivery_at=models.DateTimeField()
    reservation_expires_at=models.DateTimeField(null=True)
    version=models.PositiveIntegerField(default=1)
    courier=models.ForeignKey('User',null=True,blank=True,on_delete=models.PROTECT,related_name='deliveries')
    proposed_delivery_at=models.DateTimeField(null=True,blank=True)
    delivered_total=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    exchange_return=models.ForeignKey('ReturnRequest',null=True,blank=True,on_delete=models.PROTECT,related_name='exchange_orders')
    cash_collection_assigned=models.BooleanField(default=False)
    class Meta:
        indexes=[models.Index(fields=['client','-created_at']),models.Index(fields=['status','requested_delivery_at'])]

class OrderItem(models.Model):
    order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name='items')
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    name=models.CharField(max_length=150)
    quantity=models.PositiveIntegerField()
    unit_price=models.DecimalField(max_digits=18,decimal_places=2)
    delivered_quantity=models.PositiveIntegerField(default=0)
    returned_quantity=models.PositiveIntegerField(default=0)

class Photo(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    order=models.ForeignKey(Order,on_delete=models.PROTECT)
    uploaded_by=models.ForeignKey(User,on_delete=models.PROTECT)
    file=models.FileField(upload_to='private/%Y/%m/')
    purpose=models.CharField(max_length=30)
    content_hash=models.CharField(max_length=64)
    mime=models.CharField(max_length=30)
    size=models.PositiveIntegerField()
    created_at=models.DateTimeField(auto_now_add=True)

class LedgerEntry(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    order=models.ForeignKey(Order,null=True,blank=True,on_delete=models.PROTECT)
    kind=models.CharField(max_length=30)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    reference=models.CharField(max_length=150,unique=True)
    period=models.ForeignKey('Period',null=True,on_delete=models.PROTECT)
    reverses_entry=models.OneToOneField('self',null=True,blank=True,on_delete=models.PROTECT,related_name='reversal')
    reason=models.TextField(blank=True)
    class Meta:
        indexes=[models.Index(fields=['client','created_at']),models.Index(fields=['order','kind'])]
    def save(self,*args,**kwargs):
        if not self._state.adding: raise ValueError('Ledger entries are immutable')
        super().save(*args,**kwargs)
    def delete(self,*args,**kwargs): raise ValueError('Ledger entries are immutable')

class Payment(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    order=models.ForeignKey(Order,null=True,blank=True,on_delete=models.PROTECT)
    method=models.CharField(max_length=20)
    cash_holder_kind=models.CharField(max_length=20,blank=True)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    status=models.CharField(max_length=20,default='pending')
    reference=models.CharField(max_length=150,null=True,blank=True,unique=True)
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    confirmed_at=models.DateTimeField(null=True)
    confirmed_by=models.ForeignKey(User,null=True,on_delete=models.PROTECT,related_name='confirmed_payments')
    reversed_at=models.DateTimeField(null=True,blank=True)
    reversed_by=models.ForeignKey(User,null=True,blank=True,on_delete=models.PROTECT,related_name='reversed_payments')
    reversal_reason=models.TextField(blank=True)
    proof=models.ForeignKey(Photo,null=True,blank=True,on_delete=models.PROTECT,related_name='payment_proofs')

class PaymentAllocation(models.Model):
    payment=models.ForeignKey(Payment,on_delete=models.PROTECT,related_name='allocations')
    order=models.ForeignKey(Order,on_delete=models.PROTECT)
    amount=models.DecimalField(max_digits=18,decimal_places=2)

class CashMovement(models.Model):
    courier=models.ForeignKey(User,on_delete=models.PROTECT,related_name='cash_movements')
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    kind=models.CharField(max_length=30)
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)

class Handover(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    courier=models.ForeignKey(User,on_delete=models.PROTECT)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    accepted_amount=models.DecimalField(max_digits=18,decimal_places=2,null=True)
    status=models.CharField(max_length=20,default='pending')
    reason=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class Shift(models.Model):
    cashier=models.ForeignKey(User,on_delete=models.PROTECT)
    opened_at=models.DateTimeField(auto_now_add=True)
    closed_at=models.DateTimeField(null=True)
    expected_amount=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    counted_amount=models.DecimalField(max_digits=18,decimal_places=2,null=True)
    discrepancy=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    reason=models.TextField(blank=True)
    opening_amount=models.DecimalField(max_digits=18,decimal_places=2,default=0)

class CashboxMovement(models.Model):
    cashier=models.ForeignKey(User,on_delete=models.PROTECT)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    kind=models.CharField(max_length=30)
    created_at=models.DateTimeField(auto_now_add=True)

class ReturnRequest(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    order=models.ForeignKey(Order,on_delete=models.PROTECT)
    kind=models.CharField(max_length=20,default='return')
    items=models.JSONField()
    reason=models.TextField()
    status=models.CharField(max_length=20,default='pending')
    received=models.BooleanField(default=False)
    credited=models.BooleanField(default=False)
    disposition=models.CharField(max_length=20,default='quarantine')
    amount=models.DecimalField(max_digits=18,decimal_places=2,default=0)
    created_at=models.DateTimeField(auto_now_add=True)

class Refund(models.Model):
    id=models.UUIDField(primary_key=True,default=uuid.uuid4,editable=False)
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    order=models.ForeignKey(Order,null=True,blank=True,on_delete=models.PROTECT)
    source_reference=models.CharField(max_length=150,null=True,blank=True,unique=True)
    amount=models.DecimalField(max_digits=18,decimal_places=2)
    method=models.CharField(max_length=20)
    reason=models.TextField()
    status=models.CharField(max_length=20,default='pending')
    created_at=models.DateTimeField(auto_now_add=True)

class AuditEvent(models.Model):
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    action=models.CharField(max_length=60)
    object_id=models.CharField(max_length=80)
    object_type=models.CharField(max_length=60,blank=True)
    before=models.JSONField(default=dict)
    after=models.JSONField(default=dict)
    reason=models.TextField(blank=True)
    details=models.JSONField(default=dict)
    created_at=models.DateTimeField(auto_now_add=True)

class Notification(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    message=models.TextField()
    object_id=models.CharField(max_length=80)
    read=models.BooleanField(default=False)
    dedupe_key=models.CharField(max_length=180,null=True,blank=True,unique=True)
    payload=models.JSONField(default=dict)
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        indexes=[models.Index(fields=['user','-created_at','-id']),models.Index(fields=['user','read'])]

class DeliveryAttempt(models.Model):
    order=models.ForeignKey(Order,on_delete=models.PROTECT,related_name='attempts')
    courier=models.ForeignKey(User,on_delete=models.PROTECT)
    outcome=models.CharField(max_length=30)
    items=models.JSONField(default=list)
    photo_ids=models.JSONField(default=list)
    reason=models.TextField(blank=True)
    created_at=models.DateTimeField(auto_now_add=True)

class StockMovement(models.Model):
    product=models.ForeignKey(Product,on_delete=models.PROTECT)
    batch=models.ForeignKey(Batch,null=True,on_delete=models.PROTECT)
    return_request=models.ForeignKey(ReturnRequest,null=True,on_delete=models.PROTECT)
    quantity=models.IntegerField()
    disposition=models.CharField(max_length=30)
    reason=models.TextField()
    actor=models.ForeignKey(User,on_delete=models.PROTECT)
    created_at=models.DateTimeField(auto_now_add=True)
    resolved=models.BooleanField(default=False)
    source=models.OneToOneField('self',null=True,on_delete=models.PROTECT)

class Period(models.Model):
    client=models.ForeignKey(Client,on_delete=models.PROTECT)
    start=models.DateField()
    end_exclusive=models.DateField()
    closed_at=models.DateTimeField(null=True)
    snapshot=models.JSONField(null=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['client','start'],name='client_period_unique')]

class WeeklyReport(models.Model):
    start=models.DateField(unique=True)
    end_exclusive=models.DateField()
    payload=models.JSONField()
    created_at=models.DateTimeField(auto_now_add=True)

class Reservation(models.Model):
    order=models.ForeignKey(Order,on_delete=models.PROTECT)
    batch=models.ForeignKey(Batch,null=True,on_delete=models.PROTECT)
    quota=models.ForeignKey(Quota,null=True,on_delete=models.PROTECT)
    quantity=models.PositiveIntegerField()
    in_transit=models.BooleanField(default=False)

class Idempotency(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    method=models.CharField(max_length=10)
    path=models.CharField(max_length=200)
    key=models.UUIDField()
    body_hash=models.CharField(max_length=64)
    response=models.JSONField()
    status=models.PositiveIntegerField()
    created_at=models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['user','method','path','key'],name='unique_idempotency_scope')]

class LoginThrottle(models.Model):
    scope=models.CharField(max_length=64,primary_key=True)
    started_at=models.DateTimeField()
    failures=models.PositiveIntegerField(default=0)

