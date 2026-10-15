"""Private image validation, upload idempotency and expiring authenticated access."""
import hashlib
import io
import json
import uuid
import warnings

from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 40_000_000
PURPOSES = {'delivery', 'cash', 'return', 'exchange', 'payment'}


class PhotoValidationError(ValueError):
    pass


def sanitize_image(upload):
    if upload.size > MAX_BYTES:
        raise PhotoValidationError('Фотография должна быть не больше 10 МБ')
    content = upload.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise PhotoValidationError('Фотография должна быть не больше 10 МБ')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            probe = Image.open(io.BytesIO(content))
            fmt = probe.format
            if fmt not in {'JPEG', 'PNG', 'WEBP'}:
                raise PhotoValidationError('Разрешены JPEG, PNG и WebP')
            if probe.width * probe.height > MAX_PIXELS:
                raise PhotoValidationError('Максимальный размер — 40 мегапикселей')
            probe.verify()
            source = Image.open(io.BytesIO(content))
            source.load()
            source = ImageOps.exif_transpose(source)
            image = source.convert('RGBA' if fmt != 'JPEG' and 'A' in source.getbands() else 'RGB')
            # Rebuild pixel-only image: remove EXIF, ICC, comments and all original metadata.
            clean = Image.frombytes(image.mode, image.size, image.tobytes())
            out = io.BytesIO()
            clean.save(out, format=fmt, **({'quality':90} if fmt in {'JPEG', 'WEBP'} else {}))
            encoded = out.getvalue()
            if len(encoded) > MAX_BYTES:
                raise PhotoValidationError('После обработки фотография превышает 10 МБ')
            return {'content':encoded, 'mime':{'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[fmt],
                    'extension':{'JPEG':'jpg','PNG':'png','WEBP':'webp'}[fmt],
                    'width':clean.width,'height':clean.height,'content_hash':hashlib.sha256(encoded).hexdigest()}
    except PhotoValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise PhotoValidationError('Файл не является безопасной фотографией') from exc


def _allowed(user, order, purpose, writing=False):
    role = user.role
    if role in {'admin','accountant'}:
        return not writing or role == 'admin' or purpose in {'cash','payment'}
    if role == 'customer':
        return user.client_id == order.client_id and (not writing or purpose in {'payment','return','exchange'})
    if role == 'courier':
        assigned = order.courier_id == user.id
        active = order.status in {'ready','out_for_delivery','delivery_failed'}
        collecting = purpose == 'cash' and getattr(order,'cash_collection_assigned',False)
        if not assigned or purpose not in {'delivery', 'cash', 'return', 'exchange'}:
            return False
        if not writing:
            return active or order.status == 'delivered' or collecting
        if purpose in {'return', 'exchange'}:
            return order.status == 'delivered'
        if purpose == 'delivery':
            return active
        if purpose == 'cash':
            return active or collecting
        return False
    if role == 'cashier':
        return purpose in {'cash','payment'}
    return False


def metadata(photo, user=None, with_url=False):
    result = {'id':str(photo.id),'order_id':str(photo.order_id),'purpose':photo.purpose,
              'mime':photo.mime,'size':photo.size,'content_hash':photo.content_hash,'created_at':photo.created_at.isoformat()}
    if with_url:
        token = signing.dumps({'photo':str(photo.id),'user':str(user.id)},salt='private-photo',compress=True)
        result['url'] = f'/api/v1/files/{photo.id}/content?token={token}'
        result['expires_in'] = 300
    return result


def handle(request, route, data):
    from .models import Photo, Order, User, Idempotency
    from .views import fail
    user = request.user
    if not user.is_authenticated:
        fail('UNAUTHENTICATED','Требуется вход',401)
    if route == 'files' and request.method == 'POST':
        values = request.POST
        try:
            oid = uuid.UUID(str(values.get('order_id','')))
            key = uuid.UUID(request.headers.get('Idempotency-Key',''))
        except ValueError:
            fail('VALIDATION_ERROR','Укажите order_id и Idempotency-Key UUID')
        purpose = values.get('purpose','')
        if purpose not in PURPOSES:
            fail('VALIDATION_ERROR','Укажите назначение фотографии')
        uploads = request.FILES.getlist('files') or request.FILES.getlist('file')
        if not 1 <= len(uploads) <= 5:
            fail('VALIDATION_ERROR','Приложите от 1 до 5 фотографий')
        try:
            order = Order.objects.get(pk=oid)
        except Order.DoesNotExist:
            fail('NOT_FOUND','Заказ не найден',404)
        if not _allowed(user,order,purpose,True):
            fail('NOT_FOUND','Заказ не найден',404)
        try:
            clean = [sanitize_image(upload) for upload in uploads]
        except PhotoValidationError as exc:
            fail('VALIDATION_ERROR',str(exc))
        digest = hashlib.sha256(json.dumps({'order':str(oid),'purpose':purpose,'files':[item['content_hash'] for item in clean]},sort_keys=True).encode()).hexdigest()
        created = []
        try:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=user.pk)
                order = Order.objects.select_for_update().get(pk=oid)
                if not _allowed(user,order,purpose,True):
                    fail('NOT_FOUND','Заказ не найден',404)
                old = Idempotency.objects.filter(user=user,method='POST',path=request.path,key=key).first()
                if old:
                    if old.body_hash != digest:
                        fail('IDEMPOTENCY_CONFLICT','Ключ уже использован с другими фотографиями',409)
                    return old.response,old.status
                photos = []
                for item in clean:
                    photo = Photo(order=order,uploaded_by=user,purpose=purpose,mime=item['mime'],
                                  size=len(item['content']),content_hash=item['content_hash'])
                    photo.file.save(f'{uuid.uuid4()}.{item["extension"]}',ContentFile(item['content']),save=False)
                    created.append((photo.file.storage,photo.file.name))
                    photo.save()
                    from .services import audit
                    audit(user,'file.uploaded',photo,{'order_id':str(order.pk),'purpose':purpose,'mime':photo.mime,'size':photo.size})
                    photos.append(metadata(photo))
                result = {'items':photos}
                Idempotency.objects.create(user=user,method='POST',path=request.path,key=key,body_hash=digest,response=result,status=201)
                return result,201
        except Exception:
            for storage,name in created:
                storage.delete(name)
            raise
    parts = route.split('/')
    if len(parts) not in {2,3} or parts[0] != 'files' or request.method != 'GET':
        fail('NOT_FOUND','Файл не найден',404)
    try:
        photo = Photo.objects.select_related('order').get(pk=uuid.UUID(parts[1]))
    except (ValueError,Photo.DoesNotExist):
        fail('NOT_FOUND','Файл не найден',404)
    if not _allowed(user,photo.order,photo.purpose):
        fail('NOT_FOUND','Файл не найден',404)
    if len(parts) == 2:
        return metadata(photo,user,True),200
    if parts[2] != 'content':
        fail('NOT_FOUND','Файл не найден',404)
    try:
        claims = signing.loads(request.GET.get('token',''),salt='private-photo',max_age=300)
        if claims != {'photo':str(photo.id),'user':str(user.id)}:
            raise signing.BadSignature('wrong scope')
    except signing.BadSignature:
        fail('FORBIDDEN','Ссылка недействительна или истекла',403)
    try:
        stream = photo.file.open('rb')
    except (FileNotFoundError,OSError):
        fail('NOT_FOUND','Файл недоступен',404)
    response = FileResponse(stream,content_type=photo.mime)
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = 'inline'
    return response
