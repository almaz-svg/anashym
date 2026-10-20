"""Small, role-scoped total for the persistent debt indicator."""
from django.db.models import Sum
from .models import Client, Order, PaymentAllocation, LedgerEntry, Refund
from .services import ZERO, require


def debt_summary(user):
    require(user, 'customer', 'admin', 'cashier', 'accountant', 'courier')
    if user.role == 'courier':
        orders = Order.objects.filter(courier=user, delivered_total__gt=0)
        paid = dict(PaymentAllocation.objects.filter(order__in=orders).values('order_id').annotate(total=Sum('amount')).values_list('order_id', 'total'))
        credits = dict(LedgerEntry.objects.filter(order__in=orders, kind='return').values('order_id').annotate(total=Sum('amount')).values_list('order_id', 'total'))
        total = sum((max(ZERO, delivered + credits.get(pk, ZERO) - paid.get(pk, ZERO))
                     for pk, delivered in orders.values_list('pk', 'delivered_total')), ZERO)
        scope = 'assigned_orders'
    else:
        clients = Client.objects.filter(pk=user.client_id) if user.role == 'customer' else Client.objects.all()
        reserved = dict(Refund.objects.filter(client__in=clients, status='pending').values('client_id').annotate(total=Sum('amount')).values_list('client_id', 'total'))
        total = sum((max(ZERO, balance + reserved.get(pk, ZERO)) for pk, balance in clients.values_list('pk', 'balance')), ZERO)
        scope = 'own' if user.role == 'customer' else 'all_clients'
    return {'debt_amount': f'{total:.2f}', 'currency': 'KZT', 'scope': scope}
