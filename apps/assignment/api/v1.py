from typing import Annotated

from ninja.files import UploadedFile
from ninja.params import Form, functions
from ninja.router import Router

from apps.assignment.api.schema import (
    AssignmentAttemptSchema,
    AssignmentSessionSchema,
    AssignmentSubmissionSchema,
    AssignmentSubmitSchema,
)
from apps.assignment.models import ATTACHMENT_MAX_SIZE_MB, Assignment, Attempt
from apps.common.util import HttpRequest
from apps.learning.api.access_control import access_date, active_context

router = Router(by_alias=True)


@router.get("/{id}/session", response=AssignmentSessionSchema)
@active_context()
@access_date("assignment", "assignment")
async def get_session(request: HttpRequest, id: str):
    return await Assignment.get_session(
        assignment_id=id, learner_id=request.auth, context=request.active_context, access_date=request.access_date
    )


@router.post("/{id}/attempt", response=AssignmentAttemptSchema)
@active_context()
@access_date("assignment", "assignment")
async def start_attempt(request: HttpRequest, id: str):
    return await Attempt.start(assignment_id=id, learner_id=request.auth, context=request.active_context)


@router.post("/{id}/attempt/submit", response=AssignmentSubmissionSchema)
@active_context()
@access_date("assignment", "assignment")
async def submit_attempt(
    request: HttpRequest,
    id: str,
    data: Form[AssignmentSubmitSchema],
    files: Annotated[list[UploadedFile], functions.File(None, description=f"Max size: {ATTACHMENT_MAX_SIZE_MB}MB")],
):
    # file validtion is done in the model
    return await Attempt.submit(
        assignment_id=id, learner_id=request.auth, context=request.active_context, answer=data.answer, files=files
    )


@router.delete("/{id}/attempt/deactivate")
@active_context()
@access_date("assignment", "assignment")
async def deactivate_attempt(request: HttpRequest, id: str):
    await Attempt.deactivate(assignment_id=id, learner_id=request.auth, context=request.active_context)
