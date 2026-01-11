from time import time

from django.conf import settings
from django.utils import timezone
from django.utils.decorators import async_only_middleware
from jwt.exceptions import InvalidTokenError

from apps.account.models import BlacklistedToken, auth_cookie_options
from apps.common.util import HttpRequest, decode_token, encode_token


@async_only_middleware
def cookie_auth_middleware(get_response):
    async def middleware(request: HttpRequest):
        request.auth = ""

        try:
            refresh_token = request.COOKIES.get(settings.REFRESH_TOKEN_NAME)
            if not refresh_token:
                return await get_response(request)

            access_token = request.COOKIES.get(settings.ACCESS_TOKEN_NAME)
            if access_token:
                request.auth = decode_token(access_token).get("sub")
                return await get_response(request)

            if await BlacklistedToken.objects.filter(token=refresh_token, expires__gt=timezone.now()).aexists():
                return await get_response(request)

            user_id = decode_token(refresh_token).get("sub")
            request.auth = user_id

            max_age = settings.ACCESS_TOKEN_EXPIRE_SECONDS * 60
            expires = int(time()) + max_age
            access_token = encode_token({"sub": user_id, "exp": expires, "type": "access"})
            options = auth_cookie_options()

            response = await get_response(request)
            response.set_cookie(key=settings.ACCESS_TOKEN_NAME, value=access_token, max_age=max_age, **options)
            return response

        except InvalidTokenError:
            return await get_response(request)

    return middleware
