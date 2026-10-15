import uuid
from django.db import migrations

def opening(apps,schema_editor):
    Client=apps.get_model('shop','Client'); User=apps.get_model('shop','User'); Ledger=apps.get_model('shop','LedgerEntry')
    actor=User.objects.filter(role='admin').first()
    if not actor: return
    for client in Client.objects.exclude(balance=0):
        if not Ledger.objects.filter(client=client).exists(): Ledger.objects.create(id=uuid.uuid4(),client=client,actor=actor,kind='opening_balance',amount=client.balance,reference='opening:'+str(client.pk))

class Migration(migrations.Migration):
    dependencies=[('shop','0006_weeklyreport_returnrequest_credited_deliveryattempt_and_more')]
    operations=[migrations.RunPython(opening,migrations.RunPython.noop)]
