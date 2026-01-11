from datetime import datetime

from ninja import Schema as BaseSchema
from pydantic.alias_generators import to_camel
from pydantic.config import ConfigDict


class Schema(BaseSchema):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# https://github.com/vitalik/django-ninja/issues/347
# django-ninja ModelSchema does not working with inheritance!!!


class ContentTypeSchema(Schema):
    app_label: str
    model: str


class TimeStampedMixinSchema(Schema):
    created: datetime
    modified: datetime


class LearningObjectMixinSchema(Schema):
    created: datetime
    modified: datetime
    title: str
    description: str
    audience: str
    thumbnail: str | None
    featured: bool
    format: str
    duration_seconds: float | None
    passing_point: int
    max_attempts: int
    verification_required: bool


class GradeFieldMixinSchema(Schema):
    earned_details: dict[str, int | None]
    possible_point: int
    earned_point: int
    score: float
    passed: bool
    feedback: dict[str, str]
    completed: datetime | None
    confirmed: datetime | None


class GradingDateSchema(Schema):
    grade_due: datetime
    appeal_deadline: datetime
    confirm_due: datetime


class AccessDateSchema(Schema):
    start: datetime
    end: datetime
    archive: datetime


class ScoreStatsSchema(Schema):
    total: int
    avg_score: float
    min_score: float
    max_score: float
    max_count: int
    distribution: list[tuple[int, int]]
