"""Rich catalog data, reversible product archiving and configured payment instructions."""
import os
import uuid
from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import Batch, Product, Quota
from .services import audit, money, require, snapshot


def safe_https_url(value, field='image_url'):
    from .views import fail
    if not isinstance(value, str) or len(value) > 500:
        fail('VALIDATION_ERROR', 'Ссылка: максимум 500 символов', fields={field: ['Укажите HTTPS-ссылку']})
    value = value.strip()
    if not value:
        return ''
    try:
        URLValidator(schemes=['https'])(value)
        parts = urlsplit(value)
        if parts.username or parts.password or any(ord(char) < 32 for char in value) or '\\' in value:
            raise ValidationError('Unsafe URL')
        if not parts.hostname or parts.hostname.lower() == 'localhost' or parts.hostname.endswith('.localhost'):
            raise ValidationError('Local URL')
    except (ValidationError, ValueError):
        fail('VALIDATION_ERROR', 'Нужна корректная HTTPS-ссылка без логина и пароля', fields={field: ['Укажите безопасную HTTPS-ссылку']})
    return value


def catalog_rows(products, now=None):
    """Enrich a product page with two bounded queries instead of querying every product."""
    now = now or timezone.now()
    products = list(products)
    ids = [product.pk for product in products]
    today = timezone.localdate(now)
    by_product = defaultdict(list)
    dates = defaultdict(set)
    for batch in Batch.objects.filter(product_id__in=ids, manufactured_at__lte=now, expires_at__gt=now, quantity__gt=F('reserved')).order_by('expires_at', 'id'):
        by_product[batch.product_id].append({'id': batch.pk, 'available_qty': batch.quantity-batch.reserved,
                                           'manufactured_at': batch.manufactured_at.isoformat(), 'expires_at': batch.expires_at.isoformat()})
        dates[batch.product_id].add(today.isoformat())
    for quota in Quota.objects.filter(product_id__in=ids, date__gt=today, date__lte=today+timedelta(days=90), cutoff__gt=now, quantity__gt=F('reserved')).order_by('date'):
        dates[quota.product_id].add(quota.date.isoformat())
    return [{'id': str(product.pk), 'name': product.name, 'description': product.description,
             'image_url': product.image_url, 'shelf_life_hours': product.shelf_life_hours,
             'unit': 'portion', 'price_amount': f'{product.price:.2f}', 'currency': 'KZT',
             'available_qty': getattr(product, '_available_qty', sum(batch['available_qty'] for batch in by_product[product.pk])),
             'preorder_available_qty': getattr(product, '_quota_qty', 0), 'preparation_minutes': product.preparation_minutes,
             'available_dates': sorted(dates[product.pk]), 'batches': by_product[product.pk],
             'active': product.active} for product in products]


def _product_data(product):
    row = catalog_rows([product])[0]
    row['price'] = row['price_amount']
    return row


def _edit_product(product, data, creating=False):
    from .views import fail, validate
    fields = ['name', 'description', 'price', 'price_amount', 'preparation_minutes', 'image_url', 'shelf_life_hours', 'active']
    validate(data, ['name'] if creating else [], fields)
    if not data:
        fail('VALIDATION_ERROR', 'Укажите хотя бы одно изменяемое поле')
    if creating and not any(field in data for field in ('price', 'price_amount')):
        fail('VALIDATION_ERROR', 'Укажите цену', fields={'price_amount': ['Обязательное поле']})
    if 'price' in data and 'price_amount' in data and money(data['price']) != money(data['price_amount']):
        fail('VALIDATION_ERROR', 'Переданы разные цены')
    if 'name' in data:
        if not isinstance(data['name'], str) or not data['name'].strip() or len(data['name']) > 150:
            fail('VALIDATION_ERROR', 'Название: от 1 до 150 символов', fields={'name': ['Обязательное поле, максимум 150 символов']})
        product.name = data['name'].strip()
    if 'description' in data:
        if not isinstance(data['description'], str) or len(data['description']) > 10000:
            fail('VALIDATION_ERROR', 'Описание: максимум 10000 символов', fields={'description': ['Максимум 10000 символов']})
        product.description = data['description'].strip()
    if any(field in data for field in ('price', 'price_amount')):
        product.price = money(data.get('price_amount', data.get('price')))
    for field, minimum, maximum in [('shelf_life_hours', 1, 87600), ('preparation_minutes', 0, 10080)]:
        if field in data:
            if type(data[field]) != int or not minimum <= data[field] <= maximum:
                fail('VALIDATION_ERROR', 'Проверьте срок хранения и время приготовления', fields={field: [f'Целое число от {minimum} до {maximum}']})
            setattr(product, field, data[field])
    if 'image_url' in data:
        product.image_url = safe_https_url(data['image_url'])
    if 'active' in data:
        if type(data['active']) != bool:
            fail('VALIDATION_ERROR', 'active должен быть логическим значением', fields={'active': ['true или false']})
        product.active = data['active']
    product.full_clean()
    product.save()


def payment_instructions():
    from .views import Problem
    raw = os.getenv('KASPI_MERCHANT_URL', '')
    try:
        url = safe_https_url(raw, 'seller_url')
    except Problem:
        url = ''
    return {'method': 'kaspi', 'configured': bool(url), 'seller_url': url or None,
            'reference_required': True, 'proof_required': True,
            'instructions': ('Откройте ссылку продавца, проверьте получателя и сумму, затем приложите чек и номер операции к заказу.'
                             if url else 'Ссылка продавца пока не настроена. Запросите у администратора подтверждённый счёт Kaspi; после оплаты приложите чек и номер операции к заказу.')}


def handle_catalog(request, route, data):
    from .views import fail, validate
    method = request.method
    if route == 'payment-instructions' and method == 'GET':
        require(request.user, 'customer', 'admin', 'cashier', 'accountant')
        return payment_instructions(), 200
    parts = route.split('/')
    if route == 'catalog' and method == 'POST':
        parts = ['products']
    if parts[0] != 'products' or len(parts) > 3:
        return None
    if len(parts) == 1 and method == 'GET':
        require(request.user, 'admin', 'cashier', 'accountant')
        from .routes import page_queryset
        page, cursor = page_queryset(Product.objects.all(), request)
        return {'items': catalog_rows(page), 'next_cursor': cursor}, 200
    if method not in {'POST', 'PATCH'}:
        return None
    if len(parts) == 3 and parts[2] not in {'archive', 'restore'}:
        return None
    require(request.user, 'admin')
    with transaction.atomic():
        if len(parts) == 1:
            product = Product()
            _edit_product(product, data, creating=True)
            audit(request.user, 'products.created', product)
            return _product_data(product), 201
        try:
            product = Product.objects.select_for_update().get(pk=uuid.UUID(parts[1]))
        except (ValueError, Product.DoesNotExist):
            fail('NOT_FOUND', 'Товар не найден', 404)
        product._audit_before = snapshot(product)
        if len(parts) == 3:
            validate(data, [])
            product.active = parts[2] == 'restore'
            product.save(update_fields=['active'])
            audit(request.user, 'product.' + ('restored' if product.active else 'archived'), product)
        else:
            _edit_product(product, data)
            audit(request.user, 'product.updated', product, {'fields': sorted(data)})
        return _product_data(product), 200
