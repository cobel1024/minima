import importlib
import logging
import re
from ipaddress import IPv4Address, IPv6Address
from pathlib import Path

import msgspec
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest
from django.http.response import Http404
from ninja import NinjaAPI
from ninja.parser import Parser
from ninja.renderers import BaseRenderer

log = logging.getLogger(__name__)


class MsgSpecRenderer(BaseRenderer):
    media_type = "application/json"

    @staticmethod
    def encoder(obj):
        if isinstance(obj, (IPv4Address, IPv6Address)):
            return str(obj)
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

    def render(self, request, data, *, response_status):
        return msgspec.json.encode(data, enc_hook=self.encoder)


class MsgSpecParser(Parser):
    def parse_body(self, request: HttpRequest):
        if not request.body:
            return {}
        return msgspec.json.decode(request.body)


async def cookie_auth(request):
    # from middleware
    return getattr(request, "auth", "")


class MinimaAPI(NinjaAPI):
    def __init__(self):
        super().__init__(
            title="Minima API", version="0.1.0", auth=cookie_auth, renderer=MsgSpecRenderer(), parser=MsgSpecParser()
        )

    def get_openapi_operation_id(self, operation):
        name = operation.view_func.__name__
        module = operation.view_func.__module__
        parts = module.split(".")
        if len(parts) >= 4 and parts[0] == "apps":
            app_name = parts[1]
            version = parts[3] if len(parts) > 3 and parts[2] == "api" else "v1"
            return f"{app_name}_{version}_{name}"
        return f"{module.replace('.', '_')}_{name}"


api = MinimaAPI()

# auto discover v1 routers
apps_path = Path(__file__).parent.parent / "apps"
for app_dir in sorted(apps_path.iterdir()):
    if not app_dir.is_dir() or app_dir.name.startswith("_"):
        continue

    try:
        module = importlib.import_module(f"apps.{app_dir.name}.api.v1")
    except ModuleNotFoundError:
        continue

    if hasattr(module, "router"):
        try:
            api.add_router(f"/v1/{app_dir.name}", module.router, tags=[app_dir.name])
        except Exception as e:
            log.error(e, exc_info=True)
            continue


@api.get("/health", tags=["default"])
async def health(request):
    pass


# exception handler
@api.exception_handler(ValueError)
def value_error(request, exc):
    log.error(f"ValueError in {request.path}: {exc}", exc_info=settings.DEBUG)
    return api.create_response(request, {"detail": str(exc)}, status=400)


@api.exception_handler(ObjectDoesNotExist)
@api.exception_handler(Http404)
def does_not_exist(request, exc):
    exc_type = type(exc).__name__
    log.error(f"{exc_type} in {request.path}: {exc}", exc_info=settings.DEBUG)

    error_message = str(exc)
    match = re.search(r"No (\w+) matches", error_message)

    if match:
        error_code = f"{match.group(1).upper()}_NOT_FOUND"
    else:
        error_code = "NOT_FOUND"

    return api.create_response(request, {"detail": error_code}, status=404)
