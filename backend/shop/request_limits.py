import uuid
from django.core.exceptions import RequestDataTooBig, TooManyFieldsSent, TooManyFilesSent
from django.http import JsonResponse, UnreadablePostError
from django.http.multipartparser import MultiPartParserError


class ApiBodyLimitsMiddleware:
    """Parse multipart limits before CSRF, returning the API error envelope."""
    def __init__(self,get_response):
        self.get_response=get_response

    def __call__(self,request):
        if request.path.startswith('/api/') and (request.content_type or '').startswith('multipart/'):
            try:
                request.POST
            except (RequestDataTooBig,TooManyFieldsSent,TooManyFilesSent,MultiPartParserError,UnreadablePostError):
                return JsonResponse({'code':'VALIDATION_ERROR','message':'Не удалось принять файлы. Максимум 5 фотографий по 10 МБ.',
                    'field_errors':{'files':['Проверьте количество и размер фотографий']},'details':None,'request_id':str(uuid.uuid4())},status=422)
        return self.get_response(request)
