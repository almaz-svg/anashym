"""Single cloud web process serving built UI and Django on the same origin."""
import os
from pathlib import Path
from whitenoise import WhiteNoise
from waitress import serve
from .wsgi import application as django_application


def build_application(root=None):
    root = Path(root) if root else Path(__file__).resolve().parent.parent
    app = WhiteNoise(django_application, root=str(root / 'frontend-dist'), index_file=True)
    app.add_files(str(root / 'staticfiles'), prefix='static/')
    return app


if __name__ == '__main__':
    if not os.environ.get('RAILWAY_ENVIRONMENT_ID'):
        raise SystemExit('This entry point is for Railway only')
    serve(build_application(), host='0.0.0.0', port=int(os.environ.get('PORT', '8080')),
          threads=4, max_request_body_size=52 * 1024 * 1024,
          trusted_proxy='*', trusted_proxy_headers={'x-forwarded-proto'},
          clear_untrusted_proxy_headers=True)
