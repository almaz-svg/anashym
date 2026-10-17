"""Transient draft boundary. No storage, audit writes or production provider yet."""
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Client, Product


def _strings(value, *, limit=20, length=500):
    return isinstance(value, list) and len(value) <= limit and all(isinstance(x, str) and 0 < len(x.strip()) <= length for x in value)


def validate_draft(value, catalog, reference_date):
    """Reject unexpected model fields; never coerce guesses into valid orders."""
    if not isinstance(value, dict) or set(value) != {'items', 'delivery_date', 'questions'}:
        raise ValueError('Invalid draft envelope')
    rows = value['items']
    if not isinstance(rows, list) or len(rows) > 20 or not _strings(value['questions']):
        raise ValueError('Invalid draft rows')
    products = {p['product_id']: p for p in catalog}
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'source_text', 'product_id', 'quantity', 'unit', 'issues'}:
            raise ValueError('Invalid draft item')
        if not isinstance(row['source_text'], str) or not 1 <= len(row['source_text'].strip()) <= 4000 or not _strings(row['issues']):
            raise ValueError('Invalid item text')
        product = row['product_id']
        if product is not None and (not isinstance(product, str) or product not in products):
            raise ValueError('Unknown product')
        quantity = row['quantity']
        if quantity is not None:
            if not isinstance(quantity, str) or len(quantity) > 20 or not re.fullmatch(r'\d+(?:\.\d+)?', quantity):
                raise ValueError('Invalid quantity')
            number = Decimal(quantity)
            if not 1 <= number <= 10000 or number != number.to_integral_value():
                raise ValueError('Whole portions required')
        unit = row['unit']
        if unit is not None and (not isinstance(unit, str) or not 1 <= len(unit) <= 40 or (product is not None and unit != products[product]['unit'])):
            raise ValueError('Invalid unit')
        if any(row[k] is None for k in ('product_id', 'quantity', 'unit')) and not (row['issues'] or value['questions']):
            raise ValueError('Uncertainty requires clarification')
    day = value['delivery_date']
    if day is not None:
        if not isinstance(day, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
            raise ValueError('Invalid date')
        parsed = date.fromisoformat(day)
        if not reference_date <= parsed <= reference_date + timedelta(days=90):
            raise ValueError('Date outside ordering window')
    elif not value['questions']:
        raise ValueError('Missing date requires clarification')
    return value


def parse_order_message(actor, data, *, parser=None):
    from .views import fail, validate
    from .services import require
    require(actor, 'admin')
    # Enabling an external adapter also needs budget/privacy/rate-limit approval.
    # No environment variable can accidentally enable requests in this prototype.
    if parser is None:
        fail('AI_NOT_CONFIGURED', 'ИИ пока не подключён. Используйте ручное оформление заказа.', 503)
    validate(data, ['client_id', 'message'])
    if not isinstance(data['message'], str) or not 1 <= len(data['message'].strip()) <= 4000:
        fail('VALIDATION_ERROR', 'Сообщение должно содержать от 1 до 4000 символов')
    try:
        client = Client.objects.get(pk=uuid.UUID(str(data['client_id'])))
    except (ValueError, Client.DoesNotExist):
        fail('VALIDATION_ERROR', 'Укажите клиента')
    if client.archived or client.approval_status != 'active':
        fail('FORBIDDEN', 'Новые заказы недоступны для неодобренного или архивного клиента', 403)
    catalog = [{'product_id': str(p.pk), 'name': p.name, 'unit': 'portion'} for p in Product.objects.filter(active=True).order_by('pk')]
    today = timezone.localdate()
    payload = {'message': data['message'], 'reference_date': today.isoformat(), 'timezone': settings.TIME_ZONE, 'catalog': catalog}
    try:
        result = parser(payload, timeout=20)
        return validate_draft(result, catalog, today)
    except Exception:
        # Never include provider exception text, source message or response in logs.
        fail('AI_PARSE_FAILED', 'Не удалось разобрать сообщение. Исправьте черновик вручную.', 503)
