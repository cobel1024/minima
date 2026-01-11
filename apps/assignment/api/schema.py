from datetime import datetime
from typing import Annotated

from pydantic.fields import Field

from apps.account.api.schema import OwnerSchema
from apps.assignment.models import Submission
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


class AssignmentSchema(LearningObjectMixinSchema):
    id: str
    owner: OwnerSchema
    honor_code: HonorCodeSchema


class AssignmentSubmissionSchema(TimeStampedMixinSchema):
    id: int
    answer: str

    @staticmethod
    def resolve_answer(obj: Submission):
        return obj.cleaned_answer


class AssignmentQuestionSchema(Schema):
    id: int
    question: str
    supplement: str
    attachment_file_count: int
    attachment_file_types: list[str]
    sample_attachment: str | None
    plagiarism_threshold: int
    solution: "AssignmentSolutionSchema"


class AssignmentAttemptSchema(Schema):
    id: int
    question: AssignmentQuestionSchema
    started: datetime
    active: bool


class AssignmentGradeSchema(GradeFieldMixinSchema, TimeStampedMixinSchema):
    id: int


class AssignmentSolutionSchema(Schema):
    id: int
    reference: list[str]
    rubric_data: "RubricSchema"
    explanation: str


class RubricSchema(Schema):
    name: str
    description: str
    possible_point: int
    criteria: "list[RubricCriterionSchema]"


class RubricCriterionSchema(Schema):
    name: str
    description: str
    performance_levels: "list[PerformanceLevelSchema]"


class PerformanceLevelSchema(Schema):
    name: str
    description: str
    point: int


class AssignmentSessionSchema(Schema):
    access_date: AccessDateSchema
    grading_date: GradingDateSchema
    step: LearningSessionStep
    assignment: AssignmentSchema
    attempt: Annotated[AssignmentAttemptSchema, Field(None)]
    submission: Annotated[AssignmentSubmissionSchema, Field(None)]
    grade: Annotated[AssignmentGradeSchema, Field(None)]
    appeal: Annotated[AppealSchema, Field(None)]
    analysis: Annotated[dict[str, dict[str, int]], Field(None)]
    stats: Annotated[ScoreStatsSchema, Field(None)]
    otp_token: Annotated[str, Field(None)]


class AssignmentSubmitSchema(Schema):
    answer: str
