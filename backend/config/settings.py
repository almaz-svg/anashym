import os
from pathlib import Path
CLOUD_JOB_SECRET = os.getenv('CLOUD_JOB_SECRET', '')
BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', os.getenv('SECRET_KEY', 'local-demo-only-change-before-deployment'))
DEBUG = os.getenv('DJANGO_DEBUG', os.getenv('DEBUG', '1')) == '1'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,backend,testserver').split(',')
INSTALLED_APPS = ['django.contrib.admin','django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','shop']
MIDDLEWARE = ['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','shop.request_limits.ApiBodyLimitsMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF = 'config.urls'
TEMPLATES = [{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
if os.getenv('DB_ENGINE') == 'sqlite':
    DATABASES = {'default': {'ENGINE':'django.db.backends.sqlite3','NAME':BASE_DIR/'db.sqlite3'}}
else:
    DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql','NAME':os.getenv('DB_NAME','confectionery'),'USER':os.getenv('DB_USER','confectionery'),'PASSWORD':os.getenv('DB_PASSWORD','confectionery'),'HOST':os.getenv('DB_HOST','db'),'PORT':os.getenv('DB_PORT','5432')}}
AUTH_USER_MODEL = 'shop.User'
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
if DATABASES['default']['ENGINE'].endswith('postgresql'):
    DATABASES['default']['OPTIONS'] = {'connect_timeout':5}
USE_TZ = True
TIME_ZONE = 'Asia/Almaty'
STATIC_URL = 'static/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
CSRF_TRUSTED_ORIGINS = os.getenv('CSRF_TRUSTED_ORIGINS','http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000').split(',')
REST_FRAMEWORK = {'DEFAULT_AUTHENTICATION_CLASSES':['rest_framework.authentication.SessionAuthentication'],'URL_FORMAT_OVERRIDE':None}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_FAILURE_VIEW = 'shop.views.csrf_failure'
DATA_UPLOAD_MAX_MEMORY_SIZE = 52 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = 5
LOGGING = {
    'version':1,'disable_existing_loggers':False,
    'filters':{'sensitive_query':{'()':'shop.logging_filters.SensitiveQueryFilter'}},
    'handlers':{'safe_server':{'class':'logging.StreamHandler','filters':['sensitive_query']}},
    'loggers':{'django.server':{'handlers':['safe_server'],'level':'INFO','propagate':False}},
}

WSGI_APPLICATION = 'config.wsgi.application'
STATIC_ROOT = BASE_DIR / 'staticfiles'
if os.getenv('VERCEL') == '1' or os.getenv('DJANGO_CLOUD') == '1' or os.getenv('RAILWAY_ENVIRONMENT_ID'):
    from django.core.exceptions import ImproperlyConfigured
    from .cloud import database_from_url
    DEBUG = False
    SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
    if len(SECRET_KEY) < 50:
        raise ImproperlyConfigured('Set a strong DJANGO_SECRET_KEY for cloud deployment')
    DATABASES = {'default': database_from_url(os.getenv('DATABASE_URL') or os.getenv('POSTGRES_URL', ''))}
    ALLOWED_HOSTS = list(filter(None, [os.getenv('VERCEL_URL'), os.getenv('VERCEL_PROJECT_PRODUCTION_URL'), os.getenv('RAILWAY_PUBLIC_DOMAIN'), 'anashym-kappa.vercel.app']))
    CSRF_TRUSTED_ORIGINS = ['https://' + host for host in ALLOWED_HOSTS]
    if os.getenv('RAILWAY_ENVIRONMENT_ID'):
        ALLOWED_HOSTS.append('healthcheck.railway.app')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SUPABASE_URL = os.getenv('SUPABASE_URL', '')
    SUPABASE_STORAGE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SECRET_KEY', '')
    SUPABASE_MEDIA_BUCKET = 'bakery-private-media'
    STORAGES = {'default': {'BACKEND': 'shop.cloud_storage.SupabasePrivateStorage'},
                'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}
