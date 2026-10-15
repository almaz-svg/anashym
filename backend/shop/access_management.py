"""One-time account activation, password restoration and organization membership."""
import re
import uuid

from django.contrib.auth import logout
from django.contrib.sessions.models import Session
from django.core import signing
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from .models import Client, User
from .services import audit, require, snapshot

TOKEN_LIFETIME = 86400


def revoke_sessions(user):
    """Delete server sessions as well as invalidating their password-derived hashes."""
    keys = [session.session_key for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator()
            if session.get_decoded().get('_auth_user_id') == str(user.pk)]
    if keys:
        Session.objects.filter(session_key__in=keys).delete()


def _stamp(user):
    return salted_hmac('account-access-stamp', user.password, algorithm='sha256').hexdigest()


def invitation(user, purpose='invitation'):
    return signing.dumps({'user': str(user.pk), 'purpose': purpose, 'stamp': _stamp(user)}, salt='account-access')


def _member(user):
    return {'id': str(user.pk), 'name': user.first_name or user.username, 'phone': user.username,
            'role': user.role, 'client_id': str(user.client_id) if user.client_id else None,
            'is_active': user.is_active, 'must_change_password': user.must_change_password}


def _read_token(token):
    from .views import fail
    if not isinstance(token, str) or not token or len(token) > 4096:
        fail('VALIDATION_ERROR', 'Ссылка недействительна или истекла', fields={'token': ['Получите новую ссылку у администратора']})
    legacy = False
    try:
        try:
            claims = signing.loads(token, salt='account-access', max_age=TOKEN_LIFETIME)
            if claims.get('purpose') not in {'invitation', 'reset'}:
                raise signing.BadSignature('Wrong purpose')
            user_id = claims['user']
        except signing.BadSignature:
            claims = signing.loads(token, salt='staff-invite', max_age=TOKEN_LIFETIME)
            user_id = claims['staff']
            legacy = True
        user = User.objects.select_for_update().get(pk=uuid.UUID(user_id), is_active=True)
        expected = user.password if legacy else _stamp(user)
        if user.has_usable_password() or not constant_time_compare(expected, claims['stamp']):
            raise signing.BadSignature('Already used')
        return user
    except (signing.BadSignature, User.DoesNotExist, KeyError, ValueError, TypeError, AttributeError):
        fail('VALIDATION_ERROR', 'Ссылка недействительна, использована или истекла', fields={'token': ['Получите новую ссылку у администратора']})


def _change_password(request, data, activation=False):
    from .views import fail, validate
    using_token = activation or 'token' in data
    validate(data, ['token', 'password'] if using_token else ['current_password', 'password'])
    password = data['password']
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        fail('VALIDATION_ERROR', 'Пароль должен содержать от 12 до 128 символов', fields={'password': ['От 12 до 128 символов']})
    with transaction.atomic():
        if using_token:
            user = _read_token(data['token'])
        else:
            if not request.user.is_authenticated:
                fail('UNAUTHENTICATED', 'Требуется вход или ссылка восстановления', 401)
            user = User.objects.select_for_update().get(pk=request.user.pk, is_active=True)
            if not isinstance(data['current_password'], str) or not user.check_password(data['current_password']):
                fail('VALIDATION_ERROR', 'Текущий пароль неверен', fields={'current_password': ['Неверный пароль']})
            if user.check_password(password):
                fail('VALIDATION_ERROR', 'Новый пароль должен отличаться от текущего', fields={'password': ['Выберите другой пароль']})
        user._audit_before = snapshot(user)
        user.set_password(password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
        revoke_sessions(user)
        audit(user, 'account.password_changed', user)
    if request.user.is_authenticated:
        logout(request)
    return {'accepted': True, 'requires_login': True, 'must_change_password': False}, 200


def handle_access(request, route, data):
    """Auth routes run before login gating; business routes run inside the common dispatcher."""
    from .views import fail, validate
    method = request.method
    if route in {'auth/activate', 'auth/accept-invitation', 'auth/change-password'} and method == 'POST':
        return _change_password(request, data, activation=route != 'auth/change-password')

    parts = route.split('/')
    if len(parts) == 3 and parts[0] == 'staff' and parts[2] == 'reset-access' and method == 'POST':
        require(request.user, 'admin')
        validate(data, [], ['reason'])
        if 'reason' in data and (not isinstance(data['reason'], str) or len(data['reason']) > 1000):
            fail('VALIDATION_ERROR', 'Причина: максимум 1000 символов')
        with transaction.atomic():
            try:
                target = User.objects.select_for_update().get(pk=uuid.UUID(parts[1]), is_active=True)
            except (ValueError, User.DoesNotExist):
                fail('NOT_FOUND', 'Пользователь не найден', 404)
            target._audit_before = snapshot(target)
            target.set_unusable_password()
            target.must_change_password = True
            target.save(update_fields=['password', 'must_change_password'])
            revoke_sessions(target)
            audit(request.user, 'account.access_reset', target, {'reason': data.get('reason', '')})
            return {**_member(target), 'invitation_token': invitation(target, 'reset'), 'expires_in': TOKEN_LIFETIME}, 200

    if len(parts) != 3 or parts[0] != 'clients' or parts[2] not in {'members', 'archive', 'restore'}:
        return None
    if method not in {'GET', 'POST'} or (parts[2] != 'members' and method != 'POST'):
        return None
    require(request.user, 'admin')
    with transaction.atomic():
        try:
            company = Client.objects.select_for_update().get(pk=uuid.UUID(parts[1]))
        except (ValueError, Client.DoesNotExist):
            fail('NOT_FOUND', 'Клиент не найден', 404)
        if parts[2] in {'archive', 'restore'}:
            validate(data, [], ['reason'])
            if 'reason' in data and (not isinstance(data['reason'], str) or len(data['reason']) > 1000):
                fail('VALIDATION_ERROR', 'Причина: максимум 1000 символов')
            company._audit_before = snapshot(company)
            company.archived = parts[2] == 'archive'
            company.save(update_fields=['archived'])
            audit(request.user, 'client.' + ('archived' if company.archived else 'restored'), company, {'reason': data.get('reason', '')})
            from .routes import serialize
            return serialize(company), 200
        if method == 'GET':
            from .routes import rows
            return rows(User.objects.filter(client=company, role='customer'), request, serializer=_member), 200
        validate(data, ['phone', 'name'])
        if company.archived:
            fail('CLIENT_ARCHIVED', 'Восстановите клиента перед приглашением сотрудника', 409)
        if not isinstance(data['phone'], str) or not re.fullmatch(r'\+[1-9]\d{7,14}', data['phone']):
            fail('VALIDATION_ERROR', 'Телефон должен быть в формате E.164', fields={'phone': ['Например +77010000000']})
        if not isinstance(data['name'], str) or not data['name'].strip() or len(data['name']) > 150:
            fail('VALIDATION_ERROR', 'Укажите имя до 150 символов', fields={'name': ['Обязательное поле, максимум 150 символов']})
        if User.objects.filter(username=data['phone']).exists():
            fail('ACCOUNT_EXISTS', 'Телефон уже связан с учётной записью', 409, fields={'phone': ['Нельзя переносить существующий аккаунт между организациями']})
        try:
            with transaction.atomic():
                member = User.objects.create_user(username=data['phone'], first_name=data['name'].strip(), role='customer', client=company, must_change_password=True)
        except IntegrityError:
            fail('ACCOUNT_EXISTS', 'Телефон уже связан с учётной записью', 409)
        audit(request.user, 'client.member_invited', member, {'client_id': str(company.pk)})
        return {**_member(member), 'invitation_token': invitation(member), 'expires_in': TOKEN_LIFETIME}, 201
