from typing import Annotated

from django.conf import settings
from ninja.files import UploadedFile
from ninja.pagination import paginate
from ninja.params import Form, functions
from ninja.router import Router

from apps.common.util import HttpRequest, Pagination
from apps.discussion.api.schema import (
    DiscussionAttemptSchema,
    DiscussionPostNestedSchema,
    DiscussionPostSaveSchema,
    DiscussionPostSchema,
    DiscussionPostWithCountSchema,
    DiscussionSessionSchema,
)
from apps.discussion.models import Attempt, Discussion, Post
from apps.learning.api.access_control import access_date, active_context

router = Router(by_alias=True)


@router.get("/{id}/session", response=DiscussionSessionSchema)
@active_context()
@access_date("discussion", "discussion")
async def get_session(request: HttpRequest, id: str):
    return await Discussion.get_session(
        discussion_id=id, learner_id=request.auth, context=request.active_context, access_date=request.access_date
    )


@router.post("/{id}/attempt", response=DiscussionAttemptSchema)
@active_context()
@access_date("discussion", "discussion")
async def start_attempt(request: HttpRequest, id: str):
    return await Attempt.start(discussion_id=id, learner_id=request.auth, context=request.active_context)


@router.delete("/{id}/attempt/deactivate")
@active_context()
@access_date("discussion", "discussion")
async def deactivate_attempt(request: HttpRequest, id: str):
    await Attempt.deactivate(discussion_id=id, learner_id=request.auth, context=request.active_context)


@router.get("/{id}/post", response=list[DiscussionPostNestedSchema])
@active_context()
@access_date("discussion", "discussion")
@paginate(Pagination)
async def get_posts(request: HttpRequest, id: str):
    return Attempt.get_posts(discussion_id=id, learner_id=request.auth, context=request.active_context)


@router.post("/{id}/post", response=DiscussionPostWithCountSchema)
@active_context()
@access_date("discussion", "discussion")
async def create_post(
    request: HttpRequest,
    id: str,
    data: Form[DiscussionPostSaveSchema],
    files: Annotated[
        list[UploadedFile], functions.File(None, description=f"Max size: {settings.ATTACHMENT_MAX_SIZE_MB}MB")
    ],
):
    if files:
        Post.validate_files(files)
    return await Post.create(
        discussion_id=id, learner_id=request.auth, context=request.active_context, **data.model_dump(), files=files
    )


@router.post("/{id}/post/{postId}", response=DiscussionPostSchema)
@active_context()
@access_date("discussion", "discussion")
async def update_post(
    request: HttpRequest,
    id: str,
    post_id: Annotated[int, functions.Path(alias="postId")],
    data: Form[DiscussionPostSaveSchema],
    files: Annotated[
        list[UploadedFile], functions.File(None, description=f"Max size: {settings.ATTACHMENT_MAX_SIZE_MB}MB")
    ],
):
    if files:
        Post.validate_files(files)

    return await Post.update(
        discussion_id=id,
        learner_id=request.auth,
        context=request.active_context,
        post_id=post_id,
        **data.model_dump(exclude={"parent_id"}),
        files=files,
    )


@router.delete("/{id}/post/{postId}")
@active_context()
@access_date("discussion", "discussion")
async def delete_post(request: HttpRequest, id: str, post_id: Annotated[int, functions.Path(alias="postId")]):
    await Post.remove(discussion_id=id, learner_id=request.auth, context=request.active_context, post_id=post_id)
