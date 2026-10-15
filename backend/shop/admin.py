from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from .models import User,Client,Product,Batch,Quota,DeliveryPoint,Order,Reservation
@admin.register(User)
class ShopUserAdmin(UserAdmin):
    fieldsets=UserAdmin.fieldsets+(("Доступ",{'fields':['role','client']}),)
    def save_model(self,request,obj,form,change):
        if change and {'role','client'} & set(form.changed_data):
            from django.contrib.sessions.models import Session
            for session in Session.objects.all():
                if str(session.get_decoded().get('_auth_user_id'))==str(obj.id): session.delete()
        super().save_model(request,obj,form,change)
@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display=['name','category','approval_status','deferred_approved','credit_limit']
    readonly_fields=['reserved_credit','balance','overdue']
    def save_model(self,request,obj,form,change):
        with transaction.atomic():
            if change:
                fresh=Client.objects.select_for_update().get(pk=obj.pk)
                for field in ['reserved_credit','balance','overdue']: setattr(obj,field,getattr(fresh,field))
            super().save_model(request,obj,form,change)
    actions=['approve']
    @admin.action(description='Одобрить доступ выбранным клиентам')
    def approve(self,request,queryset):
        queryset.update(approval_status='active')
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    def get_readonly_fields(self,request,obj=None): return [f.name for f in Order._meta.fields]
    def has_add_permission(self,request): return False
    def has_delete_permission(self,request,obj=None): return False

class StockAdmin(admin.ModelAdmin):
    def get_readonly_fields(self,request,obj=None):
        if obj and Reservation.objects.filter(**{'batch' if isinstance(obj,Batch) else 'quota':obj}).exists(): return [f.name for f in obj._meta.fields]
        return ['reserved']
    def has_delete_permission(self,request,obj=None): return False
    def has_change_permission(self,request,obj=None): return obj is None
admin.site.register(Batch,StockAdmin)
admin.site.register(Quota,StockAdmin)
for model in [Product,DeliveryPoint]:
    admin.site.register(model)
