"""Reject unsafe HTTP methods before dispatching business action handlers."""

POST_ONLY_ROUTES = frozenset({
    'auth/login', 'auth/logout', 'auth/register', 'auth/activate',
    'auth/accept-invitation', 'auth/change-password', 'periods/close', 'ai/order-draft',
})

POST_ONLY_ACTIONS = {
    'payments': {'confirm', 'reject', 'reverse'},
    'handovers': {'confirm', 'reject'},
    'returns': {'receive', 'decide'},
    'refunds': {'confirm'},
    'notifications': {'read'},
    'batches': {'adjust'},
    'products': {'update', 'archive', 'restore'},
    'stock-movements': {'resolve'},
    'staff': {'role', 'reset-access'},
    'clients': {'approve', 'archive', 'restore'},
}


def require_action_method(route, method):
    """GET must never reach mutation handlers or alias an order detail suffix."""
    from .views import fail

    parts = route.split('/')
    is_action = (route in POST_ONLY_ROUTES
                 or (parts[0] == 'orders' and len(parts) > 2)
                 or (len(parts) == 3 and parts[2] in POST_ONLY_ACTIONS.get(parts[0], set())))
    if is_action and method != 'POST':
        fail('METHOD_NOT_ALLOWED', 'Для этого действия требуется POST', 405)
