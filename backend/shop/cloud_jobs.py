"""Private scheduler entry point; the shared command owns locking and transactions."""
import io
import logging

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


logger = logging.getLogger(__name__)


def _response(status, code):
    response = JsonResponse({'status': status}, status=code)
    response['Cache-Control'] = 'no-store'
    return response


@csrf_exempt
@require_POST
def run_jobs(request):
    secret = getattr(settings, 'CLOUD_JOB_SECRET', '')
    if not isinstance(secret, str) or len(secret.strip()) < 32:
        return _response('unavailable', 503)
    authorization = request.headers.get('Authorization', '')
    if not constant_time_compare(authorization, 'Bearer ' + secret):
        return _response('forbidden', 403)
    try:
        with io.StringIO() as output:
            call_command('run_background_jobs', stdout=output, stderr=output)
    except Exception:
        # Never log exception text, credentials, command output, or request headers.
        logger.warning('Scheduled background jobs failed')
        return _response('unavailable', 503)
    return _response('ok', 200)
