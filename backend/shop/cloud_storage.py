"""Private durable storage. All reads continue through Django role checks."""
import json
import mimetypes
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class SupabasePrivateStorage(Storage):
    def _request(self, path, method='GET', data=None, content_type=None):
        headers = {'Authorization': 'Bearer ' + settings.SUPABASE_STORAGE_KEY,
                   'apikey': settings.SUPABASE_STORAGE_KEY}
        if content_type:
            headers['Content-Type'] = content_type
        request = Request(settings.SUPABASE_URL.rstrip('/') + '/storage/v1/' + path,
                          data=data, headers=headers, method=method)
        return urlopen(request, timeout=20)

    def _path(self, name):
        return quote(settings.SUPABASE_MEDIA_BUCKET, safe='') + '/' + quote(name, safe='/')

    def _open(self, name, mode='rb'):
        if mode != 'rb':
            raise ValueError('Private storage supports binary reads only')
        with self._request('object/authenticated/' + self._path(name)) as response:
            return ContentFile(response.read(), name=name)

    def _save(self, name, content):
        with self._request('object/' + self._path(name), 'POST', content.read(),
                           mimetypes.guess_type(name)[0] or 'application/octet-stream'):
            return name

    def exists(self, name):
        try:
            with self._request('object/info/' + self._path(name)):
                return True
        except HTTPError as exc:
            if exc.code == 404:
                return False
            if exc.code == 400:
                try:
                    detail = json.loads(exc.read())
                except (ValueError, UnicodeDecodeError):
                    detail = {}
                if isinstance(detail, dict) and str(detail.get('statusCode')) == '404':
                    return False
            raise

    def delete(self, name):
        with self._request('object/' + quote(settings.SUPABASE_MEDIA_BUCKET, safe=''),
                           'DELETE', json.dumps({'prefixes': [name]}).encode(), 'application/json'):
            pass

    def url(self, name):
        raise NotImplementedError('Private photos require an authenticated application URL')
