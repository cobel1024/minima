from datetime import datetime
from typing import Annotated

from pydantic.fields import Field

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
from apps.discussion.models import Post
from apps.operation.api.schema import AppealSchema, HonorCodeSchema


class DiscussionSchema(LearningObjectMixinSchema):
    id: str
    owner: OwnerSchema
    honor_code: HonorCodeSchema


class DiscussionQuestionSchema(Schema):
    class DiscussionPointRequirementsSchema(Schema):
        post: Annotated[int, Field(None)]
        reply: Annotated[int, Field(None)]
        tutor_assessment: Annotated[int, Field(None)]
        post_min_characters: Annotated[int, Field(None)]
        reply_min_characters: Annotated[int, Field(None)]

    id: int
    point_requirements: DiscussionPointRequirementsSchema
    directive: str
    supplement: str


class DiscussionAttemptSchema(Schema):
    id: int
    question: DiscussionQuestionSchema
    started: datetime
    active: bool


class DiscussionGradeSchema(GradeFieldMixinSchema, TimeStampedMixinSchema):
    id: int


class DiscussionSessionSchema(Schema):
    access_date: AccessDateSchema
    grading_date: GradingDateSchema
    step: LearningSessionStep
    discussion: DiscussionSchema
    attempt: Annotated[DiscussionAttemptSchema, Field(None)]
    post_count: Annotated[DiscussionPostCountSchema, Field(None)]
    grade: Annotated[DiscussionGradeSchema, Field(None)]
    appeal: Annotated[AppealSchema, Field(None)]
    stats: Annotated[ScoreStatsSchema, Field(None)]
    otp_token: Annotated[str, Field(None)]


class DiscussionPostSchema(TimeStampedMixinSchema):
    id: int
    learner: OwnerSchema
    title: str
    body: str

    @staticmethod
    def resolve_learner(obj: Post):
        return obj.attempt.learner

    @staticmethod
    def resolve_body(obj: Post):
        return obj.cleaned_body


class DiscussionPostCountSchema(Schema):
    post: int
    reply: int
    valid_post: int
    valid_reply: int


class DiscussionPostWithCountSchema(DiscussionPostSchema):
    post_count: DiscussionPostCountSchema


class DiscussionPostNestedSchema(DiscussionPostSchema):
    children: list[DiscussionPostSchema]


class DiscussionPostSaveSchema(Schema):
    parent_id: Annotated[int, Field(None)]
    title: Annotated[str, Field(min_length=10, max_length=100)]
    body: Annotated[str, Field(max_length=5000)]  # Min is limited by qeustion.point_requirements
