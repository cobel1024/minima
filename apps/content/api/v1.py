from typing import Annotated

from django.conf import settings
from django.db.models import Count
from django.shortcuts import aget_object_or_404
from ninja.files import UploadedFile
from ninja.params import Form, functions
from ninja.router import Router

from apps.common.util import HttpRequest, PaginatedResponse
from apps.content.api.schema import (
    MediaSchema,
    NoteSaveSchema,
    NoteSchema,
    SearchedMediaSchema,
    SubtitleSchema,
    WatchInSchema,
    WatchOutSchema,
)
from apps.content.documents import get_search_suggestion
from apps.content.models import Media, Note, Subtitle, Watch
from apps.learning.api.access_control import access_date, active_context

router = Router(by_alias=True)


@router.get("/media/{id}", response=MediaSchema)
@access_date("content", "media")
async def get_media(request: HttpRequest, id: str):
    return await aget_object_or_404(
        Media.objects.annotate(subtitle_count=Count("subtitle")).select_related("owner").filter(id=id)
    )


@router.get("/media/{id}/subtitle", response=list[SubtitleSchema])
@access_date("content", "media")
async def get_subtitles(request: HttpRequest, id: str):
    return [s async for s in Subtitle.objects.filter(media_id=id)]


@router.get("/media/{id}/watch", response=WatchOutSchema)
@active_context()
@access_date("content", "media")
async def get_media_watch(request: HttpRequest, id: str):
    return await aget_object_or_404(Watch, user_id=request.auth, media_id=id, context=request.active_context)


@router.delete("/media/{id}/watch")
@active_context()
@access_date("content", "media")
async def delete_media_watch(request: HttpRequest, id: str):
    await Watch.objects.filter(media_id=id, user_id=request.auth, context=request.active_context).adelete()


@router.post("/media/{id}/watch")
@active_context()
@access_date("content", "media")
async def update_media_watch(request: HttpRequest, id: str, data: WatchInSchema):
    await Watch.update_media_watch(
        media_id=id,
        user_id=request.auth,
        context=request.active_context,
        last_position=data.last_position,
        watch_bits=data.watch_bits,
    )


@router.get("/media/{id}/note", response=NoteSchema)
@active_context()
@access_date("content", "media")
async def get_media_note(request: HttpRequest, id: str):
    return await aget_object_or_404(
        Note.objects.prefetch_related("attachments"), media_id=id, user_id=request.auth, context=request.active_context
    )


@router.post("/media/{id}/note", response=NoteSchema)
@active_context()
@access_date("content", "media")
async def save_media_note(
    request: HttpRequest,
    id: str,
    data: Form[NoteSaveSchema],
    files: Annotated[
        list[UploadedFile], functions.File(None, description=f"Max size: {settings.ATTACHMENT_MAX_SIZE_MB}MB")
    ],
):
    if files:
        Note.validate_files(files)
    return await Note.upsert(
        media_id=id, user_id=request.auth, context=request.active_context, note=data.note, files=files
    )


@router.get("/searchsuggestion", response=list[str])
def search_suggestion(request: HttpRequest, q: str, limit: int = 10):
    return get_search_suggestion(q=q, limit=limit)


@router.get("/search", response=PaginatedResponse[SearchedMediaSchema])
async def search(
    request: HttpRequest,
    page: Annotated[int, functions.Query(1, ge=1)],
    size: Annotated[int, functions.Query(settings.DEFAULT_PAGINATION_SIZE, gte=1, le=100)],
    q: str = "",
):
    return await Media.search(q=q, page=page, size=size)
