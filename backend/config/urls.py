from django.contrib import admin
from django.urls import path
from shop.views import endpoint
from shop.health import live,ready
urlpatterns=[path('live',live),path('ready',ready),path('admin/',admin.site.urls),path('api/v1/<path:route>',endpoint)]
