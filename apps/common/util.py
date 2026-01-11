import math
import random
import time
from datetime import datetime
from enum import IntEnum
from typing import TYPE_CHECKING, Annotated, Any, NotRequired, TypedDict, cast
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import jwt
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.postgres.forms import SimpleArrayField
from django.db import connection
from django.db.models import Avg, Count, FloatField, Max, Min, Model, Value
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.http.request import HttpRequest as DjangoHttpRequest
from ninja.pagination import AsyncPaginationBase
from ninja.params import functions

from apps.common.error import ErrorCode
from apps.common.schema import Schema

CHARSET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
OFFSET = 1609459200


if TYPE_CHECKING:
    from apps.account.models import User


def tuid(length: int = 12):
    # recommendation: minimum length 9

    timestamp = int(time.time()) - OFFSET
    base = len(CHARSET)
    time_encoded = ""
    t = timestamp

    if t == 0:
        time_encoded = "0"

    while t > 0:
        t, rem = divmod(t, base)
        time_encoded = CHARSET[rem] + time_encoded

    time_part = time_encoded.rjust(4, "0")

    if len(time_part) > length:
        time_part = time_part[-length:]

    rand_len = max(0, length - len(time_part))
    rand_part = "".join(random.choices(CHARSET, k=rand_len))
    return time_part + rand_part


class TokenDict(TypedDict):
    sub: str
    exp: int
    type: str
    to: NotRequired[str]


def encode_token(payload: TokenDict, algorithm: str = "HS256"):
    return jwt.encode({**payload}, settings.SECRET_KEY, algorithm=algorithm)


def decode_token(token: str, algorithm: str = "HS256") -> TokenDict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[algorithm])


class AccessDeniedError(Exception):
    def __init__(self, message: str, status_code: int = 403):
        self.message = message
        self.status_code = status_code


class ArrayField(SimpleArrayField):
    # https://github.com/unfoldadmin/django-unfold/issues/825
    def prepare_value(self, value: object):
        if value is None:
            return None
        if isinstance(value, list):
            return value
        return super().prepare_value(value)


class AccessDate(TypedDict):
    start: datetime
    end: datetime
    archive: datetime


class GradingDate(TypedDict):
    grade_due: datetime
    appeal_deadline: datetime
    confirm_due: datetime


class HttpRequest(DjangoHttpRequest):
    auth: str  # from auth middleware
    access_date: "AccessDate"  # set by access_date decorator
    active_context: str  # set by active_context decorator


class AuthenticatedRequest(HttpRequest):
    user: User


class OtpTokenDict(TypedDict):
    consumer_id: str
    app_label: str
    model: str
    user_id: str


class PaginatedResponse[T](Schema):
    items: list[T]
    count: int
    size: int
    page: int
    pages: int


async def offset_paginate(queryset, *, page: int, size: int):
    offset = (page - 1) * size
    count = await queryset.acount()
    pages = math.ceil(count / size) if count > 0 else 1
    items = [item async for item in queryset[offset : offset + size]]
    return {"items": items, "count": count, "size": size, "page": page, "pages": pages}


class Pagination(AsyncPaginationBase):
    class Input(AsyncPaginationBase.Input):
        page: Annotated[int, functions.Query(1, ge=1)]
        size: Annotated[int, functions.Query(settings.DEFAULT_PAGINATION_SIZE, gte=1, le=100)]

    class Output(AsyncPaginationBase.Output):
        items: list[Any]
        count: int
        size: int
        page: int
        pages: int

    def paginate_queryset(self, *args, **kwargs):
        pass

    async def apaginate_queryset(self, queryset: QuerySet, pagination: Any, request: DjangoHttpRequest, **params: Any):
        return await offset_paginate(queryset, page=pagination.page, size=pagination.size)


def no_auth_required(request: HttpRequest):
    if request.auth:
        raise ValueError(ErrorCode.ALREADY_LOGGED_IN)
    return True


class LearningSessionStep(IntEnum):
    READY = 0
    SITTING = 1
    TIMEOUT = 2
    GRADING = 3
    REVIEWING = 4
    FINAL = 5


class ScoreStatsDict(TypedDict):
    total: int
    avg_score: float
    min_score: float
    max_score: float
    max_count: int
    distribution: list[tuple[int, int]]


SCORE_BUCKET_SIZE = 5


async def get_score_stats(
    *, base_model: type[Model], base_model_id: str, grade_model: type[Model], attempt_model: type[Model]
) -> ScoreStatsDict:
    queryset = grade_model.objects.filter(**{
        f"{attempt_model._meta.model_name}__{base_model._meta.model_name}_id": base_model_id
    })
    stats_data = await queryset.aaggregate(
        total=Count("id"),
        avg_score=Coalesce(Avg("score"), Value(0.0), output_field=FloatField()),
        min_score=Coalesce(Min("score"), Value(0.0), output_field=FloatField()),
        max_score=Coalesce(Max("score"), Value(0.0), output_field=FloatField()),
    )

    def _execute():
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                    SELECT FLOOR(g.score / {SCORE_BUCKET_SIZE}) * {SCORE_BUCKET_SIZE} as bucket, COUNT(*) as count
                    FROM {grade_model._meta.db_table} g
                    JOIN {attempt_model._meta.db_table} a ON g.attempt_id = a.id
                    WHERE a.{base_model._meta.model_name}_id = %s AND g.score IS NOT NULL
                    GROUP BY FLOOR(g.score / {SCORE_BUCKET_SIZE}) * {SCORE_BUCKET_SIZE}
                    ORDER BY bucket
                """,
                [base_model_id],
            )
            return cursor.fetchall()

    distribution = await sync_to_async(_execute)()
    max_count = max((count for _, count in distribution), default=0)
    stats_data.update(distribution=distribution, max_count=max_count)

    return cast(ScoreStatsDict, stats_data)


def add_query_params(url: str, **params):
    url_parts = list(urlparse(url))
    query = dict(parse_qsl(url_parts[4]))
    query.update(params)
    url_parts[4] = urlencode(query)
    return urlunparse(url_parts)


def openapi_query_param(*, func, name: str, schema_type: str, required: bool, nullable: bool):
    if not hasattr(func, "_ninja_contribute_to_operation"):
        func._ninja_contribute_to_operation = []

    def contribute_to_operation(operation):
        if operation.openapi_extra is None:
            operation.openapi_extra = {}
        if "parameters" not in operation.openapi_extra:
            operation.openapi_extra["parameters"] = []

        existing_names = {p["name"] for p in operation.openapi_extra["parameters"]}
        if name not in existing_names:
            operation.openapi_extra["parameters"].append({
                "in": "query",
                "name": name,
                "schema": {"type": schema_type, "nullable": nullable},
                "required": required,
            })

    func._ninja_contribute_to_operation.append(contribute_to_operation)
