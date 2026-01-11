from typing import Annotated

from django.conf import settings
from ninja.params import functions
from ninja.router import Router

from apps.common.util import HttpRequest, PaginatedResponse
from apps.learning.api.schema import (
    CatalogItemEnrollSchema,
    CatalogItemSchema,
    CatalogSchema,
    EnrollmentSchema,
    EnrollmentSuccessSchema,
    LearningRecordSchema,
)
from apps.learning.models import Catalog, Enrollment

router = Router(by_alias=True)


@router.get("/enrollment", response=PaginatedResponse[EnrollmentSchema])
async def get_enrolled(
    request: HttpRequest,
    page: Annotated[int, functions.Query(1, ge=1)],
    size: Annotated[int, functions.Query(settings.DEFAULT_PAGINATION_SIZE, gte=1, le=100)],
):
    # Custom pagination with generic relationship
    return await Enrollment.get_enrolled(user_id=request.auth, page=page, size=size)


@router.delete("/enrollment/{id}")
async def unenroll(request: HttpRequest, id: int):
    await Enrollment.deactivate(id=id, user_id=request.auth)


@router.get("/record", response=LearningRecordSchema)
async def get_records(request: HttpRequest):
    return await Enrollment.get_records(request.auth)


@router.get("/catalog", response=list[CatalogSchema])
async def get_catalogs(request: HttpRequest):
    return [c async for c in Catalog.get_catalogs(request.auth)]


@router.get("/catalog/{id}/item", response=PaginatedResponse[CatalogItemSchema])
async def get_catalog_items(
    request: HttpRequest,
    id: int,
    page: Annotated[int, functions.Query(1, ge=1)],
    size: Annotated[int, functions.Query(settings.DEFAULT_PAGINATION_SIZE, gte=1, le=100)],
):
    # Custom pagination with generic relationship
    return await Catalog.get_items(catalog_id=id, user_id=request.auth, page=page, size=size)


@router.post("/catalog/{id}/item/enroll", response=EnrollmentSuccessSchema)
async def enroll_catalog_item(request: HttpRequest, id: int, data: CatalogItemEnrollSchema):
    return await Catalog.enroll_catalog_item(
        catalog_id=id,
        user_id=request.auth,
        content_id=data.content_id,
        app_label=data.app_label,
        model=data.model,
        enrolled_by_id=request.auth,
    )
