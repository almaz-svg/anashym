from django.contrib import admin
from django.urls import path
from shop.views import endpoint
from shop.health import live,ready
from shop.cloud_jobs import run_jobs
urlpatterns=[path('live',live),path('ready',ready),path('admin/',admin.site.urls),path('api/internal/jobs',run_jobs),path('api/v1/<path:route>',endpoint)]
