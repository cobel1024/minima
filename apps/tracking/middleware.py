import pghistory
from django.core.handlers.asgi import ASGIRequest as DjangoASGIRequest
from django.core.handlers.wsgi import WSGIRequest as DjangoWSGIRequest
from ipware.ip import get_client_ip
from pghistory import config
from ua_parser import parse


class DjangoRequest:
    def __setattr__(self, attr: str, value):
        # cf. pghistory.middleware.HistoryMiddleware
        if attr == "user":
            if hasattr(value, "_meta"):
                pghistory.context(user_id=value.pk, is_admin=value.is_superuser or value.is_staff)

        return super().__setattr__(attr, value)


class WSGIRequest(DjangoRequest, DjangoWSGIRequest):
    pass


class ASGIRequest(DjangoRequest, DjangoASGIRequest):
    pass


class HistoryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in config.middleware_methods():
            # request context
            ua = parse(request.headers.get("user-agent", ""))  # by django-upgrade
            context = {
                "ip": get_client_ip(request)[0],
                "device": ua.device.family if ua.device else None,
                "os": ua.os.family if ua.os else None,
                "browser": ua.user_agent.family if ua.user_agent else None,
                "auth_id": getattr(request, "auth", None),  # from account middleware
                "url": request.path,
            }

            if user := getattr(request, "user", None):
                if user.is_authenticated:
                    context.update(user_id=user.pk, is_admin=user.is_superuser or user.is_staff)

            with pghistory.context(**context):
                if isinstance(request, DjangoWSGIRequest):
                    request.__class__ = WSGIRequest
                elif isinstance(request, DjangoASGIRequest):
                    request.__class__ = ASGIRequest

                return self.get_response(request)
        else:
            return self.get_response(request)
