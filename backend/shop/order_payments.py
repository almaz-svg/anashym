"""Actual confirmed payments, including usable prepayments before delivery."""
from django.db.models import Sum

from .models import Payment, PaymentAllocation
from .services import ZERO, available_advances


def prepaid_breakdowns(client_id):
    by_payment, _ = available_advances(client_id)
    result = {}
    for payment in Payment.objects.filter(pk__in=by_payment).values('pk', 'order_id', 'method'):
        if payment['order_id'] is None:
            continue
        amounts = result.setdefault(payment['order_id'], {'cash': ZERO, 'kaspi': ZERO})
        amounts[payment['method']] += by_payment[payment['pk']]
    return result


def order_payment_amounts(order):
    if hasattr(order, '_payment_amounts'):
        return order._payment_amounts
    if not order.delivered_total:
        return prepaid_breakdowns(order.client_id).get(order.pk, {'cash': ZERO, 'kaspi': ZERO})
    amounts = {'cash': ZERO, 'kaspi': ZERO}
    for row in PaymentAllocation.objects.filter(order=order, payment__status='confirmed').values('payment__method').annotate(total=Sum('amount')):
        amounts[row['payment__method']] = row['total']
    return amounts
