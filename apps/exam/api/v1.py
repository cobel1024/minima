from django.utils import timezone
from ninja.router import Router

from apps.common.util import HttpRequest
from apps.exam.api.schema import ExamAttemptAnswersSchema, ExamAttemptSchema, ExamSessionSchema, ExamSubmissionSchema
from apps.exam.models import Attempt, Exam
from apps.learning.api.access_control import access_date, active_context

router = Router(by_alias=True)


@router.get("/{id}/session", response=ExamSessionSchema)
@active_context()
@access_date("exam", "exam")
async def get_session(request: HttpRequest, id: str):
    return await Exam.get_session(
        exam_id=id, learner_id=request.auth, context=request.active_context, access_date=request.access_date
    )


@router.post("/{id}/attempt", response=ExamAttemptSchema)
@active_context()
@access_date("exam", "exam")
async def start_attempt(request: HttpRequest, id: str):
    return await Attempt.start(exam_id=id, learner_id=request.auth, context=request.active_context)


@router.post("/{id}/attempt/save")
@active_context()
@access_date("exam", "exam")
async def save_answers(request: HttpRequest, id: str, data: ExamAttemptAnswersSchema):
    await Attempt.save_answers(
        exam_id=id, learner_id=request.auth, context=request.active_context, answers=data.model_dump()
    )


@router.post("/{id}/attempt/submit", response=ExamSubmissionSchema)
@active_context()
@access_date("exam", "exam")
async def submit_attempt(request: HttpRequest, id: str, data: ExamAttemptAnswersSchema):
    return await Attempt.submit(
        exam_id=id, learner_id=request.auth, context=request.active_context, answers=data.model_dump()
    )


@router.delete("/{id}/attempt/deactivate")
@active_context()
@access_date("exam", "exam")
async def deactivate_attempt(request: HttpRequest, id: str):
    await Attempt.deactivate(exam_id=id, learner_id=request.auth, context=request.active_context)


@router.get("/timestamp", response=float, auth=None)
async def get_timestamp(request: HttpRequest):
    return timezone.now().timestamp()
