from datetime import datetime
from typing import Annotated, Literal

from pydantic.fields import Field

from apps.account.api.schema import OwnerSchema
from apps.common.schema import AccessDateSchema, LearningObjectMixinSchema, Schema, TimeStampedMixinSchema
from apps.course.models import Course
from apps.operation.api.schema import FAQItemSchema, HonorCodeSchema
from apps.partner.api.schema import PartnerSchema

LevelType = Literal["beginner", "intermediate", "advanced", "common"]


class CourseDetailSchema(LearningObjectMixinSchema):
    class CourseCategorySchema(Schema):
        id: int
        name: str
        ancestors: list[str]

    class CourseCertificateSchema(Schema):
        id: int
        name: str
        thumbnail: str
        description: str
        issuer: PartnerSchema

    class CourseInstructorSchema(Schema):
        id: int
        name: str
        about: str
        bio: list[str]
        avatar: str | None
        lead: bool

    class RelatedCourseSchema(Schema):
        id: str
        title: str
        description: str
        thumbnail: str | None

    id: str
    owner: OwnerSchema
    objective: str
    preview_url: str | None
    effort_hours: int
    level: LevelType

    faq_items: list[FAQItemSchema]
    categories: list[CourseCategorySchema]
    certificates: list[CourseCertificateSchema]
    instructors: list[CourseInstructorSchema]
    related_courses: list[RelatedCourseSchema]

    @staticmethod
    def resolve_faq_items(obj: Course):
        return obj.faq.faqitem_set.all() if obj.faq else []

    @staticmethod
    def resolve_lessons(obj: Course):
        return obj.lesson_set.all()


class CourseEngagementSchema(TimeStampedMixinSchema):
    class CourseGradebookSchema(TimeStampedMixinSchema):
        id: int
        details: dict[str, float]
        score: float
        completion_rate: float
        passed: bool

    id: int
    gradebook: Annotated[CourseGradebookSchema, Field(None)]
    active: bool


class CourseSchema(LearningObjectMixinSchema):
    class LessonSchema(Schema):
        class LessonMediaSchema(Schema):
            id: str
            title: str
            thumbnail: str | None
            format: str
            ordering: int

        id: int
        medias: list[LessonMediaSchema]
        start_date: datetime
        end_date: datetime
        ordering: int
        title: str
        description: str

    class GradingCriterionSchema(Schema):
        title: str
        app_label: str
        model: str
        passing_point: int
        weight: float
        normalized_weight: float
        item_id: str
        start_date: datetime | None
        end_date: datetime | None

    id: str
    honor_code: HonorCodeSchema
    grading_criteria: list[GradingCriterionSchema]
    lessons: list[LessonSchema]
    objective: str
    preview_url: str | None
    effort_hours: int
    level: LevelType

    @staticmethod
    def resolve_lessons(obj: Course):
        return obj.lesson_set.all()


class CourseSessionSchema(Schema):
    access_date: AccessDateSchema
    course: CourseSchema
    engagement: Annotated[CourseEngagementSchema, Field(None)]
    otp_token: Annotated[str, Field(None)]


class CourseCertificateRequestSchema(Schema):
    certificate_id: int
