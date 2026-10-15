"""Generate one overdue reminder per recipient/client/business day."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from shop.models import Client, Notification, User
from shop.services import overdue_amount


class Command(BaseCommand):
    help = 'Create deduplicated overdue notifications using the authoritative debt calculation'

    def handle(self, *args, **options):
        day = timezone.localdate().isoformat()
        staff = list(User.objects.filter(is_active=True, role__in=['admin', 'accountant']).values_list('id', flat=True))
        created = 0
        for client in Client.objects.filter(balance__gt=0).iterator(chunk_size=100):
            amount = overdue_amount(client)
            if amount <= 0:
                continue
            recipients = set(staff)
            recipients.update(User.objects.filter(client=client, is_active=True).values_list('id', flat=True))
            for recipient in recipients:
                _, added = Notification.objects.get_or_create(
                    dedupe_key=f'overdue:{day}:{client.pk}:{recipient}',
                    defaults={'user_id': recipient, 'object_id': str(client.pk), 'message': 'debt.overdue',
                              'payload': {'client_name': client.name, 'overdue_amount': f'{amount:.2f}', 'currency': 'KZT', 'as_of': day}},
                )
                created += added
        self.stdout.write(f'Created {created} overdue reminders')
