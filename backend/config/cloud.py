"""Cloud database configuration; the app never uses Supabase's public schema."""
from urllib.parse import unquote, urlsplit
from django.core.exceptions import ImproperlyConfigured


def database_from_url(value):
    try:
        url = urlsplit(value)
        if url.scheme not in {'postgres', 'postgresql'} or not url.hostname or not url.username or not url.path.strip('/'):
            raise ValueError()
        return {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': unquote(url.path.lstrip('/')), 'USER': unquote(url.username),
            'PASSWORD': unquote(url.password or ''), 'HOST': url.hostname,
            'PORT': str(url.port or 5432), 'CONN_MAX_AGE': 0,
            'CONN_HEALTH_CHECKS': True, 'DISABLE_SERVER_SIDE_CURSORS': True,
            'OPTIONS': {'sslmode': 'require', 'connect_timeout': 10,
                        'prepare_threshold': None, 'options': '-c search_path=bakery'},
        }
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured('A valid PostgreSQL URL is required for cloud deployment') from exc
