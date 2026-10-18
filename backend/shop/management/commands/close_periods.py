from django.core.management.base import BaseCommand,CommandError
from django.db import transaction
from shop.models import User
from shop.routes import handle
from types import SimpleNamespace

class Command(BaseCommand):
    help='Close finished client periods with immutable snapshots; safe to repeat'
    def add_arguments(self,parser): parser.add_argument('--as-of')
    def handle(self,*args,**options):
        actor=User.objects.filter(role='accountant',is_active=True).first() or User.objects.filter(role='admin',is_active=True).first()
        if not actor: raise CommandError('No active authorized staff account')
        data={'as_of':options['as_of']} if options.get('as_of') else {}
        with transaction.atomic(): result,_=handle(SimpleNamespace(user=actor,method='POST'), 'periods/close', data)
        self.stdout.write('Closed '+str(result['closed_count'])+' periods')
