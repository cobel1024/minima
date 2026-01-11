from django.conf import settings
from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from apps.competency.views import verify_certificate
from minima.api import api

urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/", api.urls),
    path("certificate/verify/", verify_certificate, name="verify_certificate"),
]

urlpatterns += i18n_patterns(path("admin/", admin.site.urls))


if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
