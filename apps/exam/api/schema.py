from datetime import datetime
from typing import Annotated, Literal

from pydantic.fields import Field
from pydantic.root_model import RootModel

from apps.account.api.schema import OwnerSchema
from apps.common.schema import (
    AccessDateSchema,
    GradeFieldMixinSchema,
    GradingDateSchema,
    LearningObjectMixinSchema,
    Schema,
    ScoreStatsSchema,
    TimeStampedMixinSchema,
)
from apps.common.util import LearningSessionStep
from apps.operation.api.schema import AppealSchema, HonorCodeSchema


class ExamQuestionPoolSchema(Schema):
    id: int
    composition: dict[str, int]


class ExamSchema(LearningObjectMixinSchema):
    id: str
    owner: OwnerSchema
    honor_code: HonorCodeSchema
    question_pool: ExamQuestionPoolSchema
    duration_seconds: int


class ExamSubmissionSchema(TimeStampedMixinSchema):
    id: int
    answers: dict[str, str]


class ExamQuestionSchema(Schema):
    id: int
    format: Literal["single_choice", "text_input", "number_input", "essay"]
    options: list[str]
    question: str
    supplement: str
    point: int


class ExamAttemptSchema(Schema):
    id: int
    saved_answers: dict[str, str] | None
    questions: list[ExamQuestionSchema]
    started: datetime
    active: bool


class ExamGradeSchema(GradeFieldMixinSchema, TimeStampedMixinSchema):
    id: int
    earned_details: dict[str, int | None]
    feedback: dict[str, str]
    completed: datetime | None
    confirmed: datetime | None


class ExamSolutionSchema(Schema):
    id: int
    correct_answers: list[str]
    reference: list[str]
    correct_criteria: str
    explanation: str


class ExamSessionSchema(Schema):
    access_date: AccessDateSchema
    grading_date: GradingDateSchema
    step: LearningSessionStep
    exam: ExamSchema
    attempt: Annotated[ExamAttemptSchema, Field(None)]
    submission: Annotated[ExamSubmissionSchema, Field(None)]
    grade: Annotated[ExamGradeSchema, Field(None)]
    solutions: Annotated[dict[str, ExamSolutionSchema], Field(None)]
    appeals: Annotated[dict[str, AppealSchema], Field(None)]
    analysis: Annotated[dict[str, dict[str, int]], Field(None)]
    stats: Annotated[ScoreStatsSchema, Field(None)]
    otp_token: Annotated[str, Field(None)]


class ExamAttemptAnswersSchema(RootModel[dict[str, Annotated[str, Field(min_length=1)]]]):
    pass
