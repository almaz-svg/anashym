"""Read-only profile and accounting summaries for the authenticated customer."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import DecimalField, Exists, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from django.utils import timezone

from .models import Client, LedgerEntry, Order, Payment, PaymentAllocation
from .services import ZERO, overdue_amount, require, financial_amounts


BUSINESS_TIMEZONE = ZoneInfo('Asia/Almaty')


def profile_period(params, now):
    from .views import fail

    if set(params) - {'from', 'to'}:
        fail('VALIDATION_ERROR', 'Допустимы только даты from и to')
    if 'from' not in params and 'to' not in params:
        today = timezone.localdate(now, timezone=BUSINESS_TIMEZONE)
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
    else:
        try:
            start = date.fromisoformat(params['from'])
            end = date.fromisoformat(params['to'])
            if start.isoformat() != params['from'] or end.isoformat() != params['to']:
                raise ValueError()
            if not 0 <= (end - start).days < 366:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            fail('VALIDATION_ERROR', 'Укажите from и to в формате YYYY-MM-DD, период до 366 дней')
    try:
        lower = datetime.combine(start, time.min, tzinfo=BUSINESS_TIMEZONE)
        upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=BUSINESS_TIMEZONE)
    except OverflowError:
        fail('VALIDATION_ERROR', 'Некорректный период')
    return start, end, lower, upper


def customer_profile(user, params):
    from .views import fail

    require(user, 'customer')
    if not user.client_id:
        fail('FORBIDDEN', 'Профиль клиента не найден', 403)
    now = timezone.now()
    start, end, lower, upper = profile_period(params, now)
    client = Client.objects.get(pk=user.client_id)
    amounts = financial_amounts(client)
    entries = LedgerEntry.objects.filter(client=client, created_at__gte=lower, created_at__lt=upper)
    flows = entries.aggregate(
        delivered=Sum('amount', filter=Q(kind='delivery')),
        paid=Sum('amount', filter=Q(kind__in=['payment','payment_reversal'])),
        returned=Sum('amount', filter=Q(kind='return')),
        refunded=Sum('amount', filter=Q(kind='refund')),
    )
    delivered = flows['delivered'] or ZERO
    paid = -(flows['paid'] or ZERO)
    returned = -(flows['returned'] or ZERO)
    refunded = flows['refunded'] or ZERO

    # The selected deliveries define the cohort. Their remaining obligations use
    # all confirmed allocations and return credits, even after the selected dates.
    deliveries = entries.filter(kind='delivery', order_id=OuterRef('pk'))
    payments = PaymentAllocation.objects.filter(
        order_id=OuterRef('pk'), payment__client=client, payment__status='confirmed',
    ).values('order_id').annotate(total=Sum('amount')).values('total')
    credits = LedgerEntry.objects.filter(
        client=client, order_id=OuterRef('pk'), kind='return',
    ).values('order_id').annotate(total=Sum('amount')).values('total')
    amount_field = DecimalField(max_digits=18, decimal_places=2)
    orders = Order.objects.filter(client=client).annotate(
        in_period=Exists(deliveries),
        paid=Coalesce(Subquery(payments), Value(ZERO), output_field=amount_field),
        credits=Coalesce(Subquery(credits), Value(ZERO), output_field=amount_field),
    ).filter(in_period=True)
    outstanding = orders.aggregate(total=Sum(Greatest(
        F('delivered_total') + F('credits') - F('paid'), Value(ZERO), output_field=amount_field,
    )))['total'] or ZERO
    pending = Payment.objects.filter(client=client, status='pending').aggregate(total=Sum('amount'))['total'] or ZERO
    with timezone.override(BUSINESS_TIMEZONE):
        overdue = overdue_amount(client)

    return {
        'profile': {
            'name': client.name,
            'contact_name': user.get_full_name(),
            'phone': user.username,
            'category': client.category,
            'category_other': client.category_other,
            'description': client.description,
            'approval_status': client.approval_status,
            'deferred_approved': client.deferred_approved,
            'archived': client.archived,
            'preferred_payment_mode': client.preferred_payment_mode,
            'expected_order_quantity': client.expected_order_quantity,
            'expected_order_frequency': client.expected_order_frequency,
            'period_days': client.period_days,
            'credit_limit_amount': f'{client.credit_limit:.2f}',
        },
        'from': start.isoformat(),
        'to': end.isoformat(),
        'generated_at': now.isoformat(),
        'currency': 'KZT',
        'balance': {
            'debt_amount': f'{amounts["debt"]:.2f}',
            'advance_amount': f'{amounts["advance"]:.2f}',
            'reserved_refund_amount': f'{amounts["reserved_refund"]:.2f}',
            'overdue_amount': f'{overdue:.2f}',
            'unconfirmed_payment_amount': f'{pending:.2f}',
        },
        'period': {
            'delivered_amount': f'{delivered:.2f}',
            'return_credit_amount': f'{returned:.2f}',
            'turnover_amount': f'{delivered - returned:.2f}',
            'paid_amount': f'{paid:.2f}',
            'refund_amount': f'{refunded:.2f}',
            'outstanding_amount': f'{outstanding:.2f}',
        },
    }, 200
