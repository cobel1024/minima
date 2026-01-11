from datetime import datetime
from typing import Annotated, Literal

from django.conf import settings
from ninja import FilterLookup, FilterSchema
from pydantic import Field, RootModel, model_validator

from apps.account.api.schema import OwnerSchema
from apps.common.error import ErrorCode
from apps.common.schema import ContentTypeSchema, Schema, TimeStampedMixinSchema
from apps.operation.models import Appeal, Comment, Inquiry


class AnnounceSchema(TimeStampedMixinSchema):
    id: int
    title: str
    body: str
    pinned: bool
    read: datetime | None


class HonorCodeSchema(TimeStampedMixinSchema):
    id: int
    title: str
    code: str


class FAQItemSchema(TimeStampedMixinSchema):
    id: int
    ordering: int
    question: str
    answer: str
    active: bool


class InquirySchema(TimeStampedMixinSchema):
    class InquiryResponseSchema(TimeStampedMixinSchema):
        id: int
        writer: OwnerSchema
        answer: str
        solved: datetime | None

    id: int
    responses: list[InquiryResponseSchema]
    title: str
    question: str
    content_type: ContentTypeSchema
    content_id: str | int

    @staticmethod
    def resolve_question(obj: Inquiry):
        return obj.cleaned_question


class InquirySavedSchema(TimeStampedMixinSchema):
    id: int
    title: str
    question: str


class InquiryFilterSchema(FilterSchema, Schema):
    content_id: Annotated[str | int | None, FilterLookup(None)] = None
    app_label: Annotated[str | None, FilterLookup(q="content_type__app_label")] = None
    model: Annotated[str | None, FilterLookup(q="content_type__model")] = None


class InquiryCreateSchema(Schema):
    title: Annotated[str, Field(min_length=1)]
    question: Annotated[str, Field(min_length=1)]
    app_label: str
    model: str
    content_id: str | int


class InquiryUpdateSchema(Schema):
    title: Annotated[str, Field(min_length=1)]
    question: Annotated[str, Field(min_length=1)]


class MessageSchema(TimeStampedMixinSchema):
    id: int
    recipients: list[str]
    channel: Literal["email", "text", "fcm"]
    group: str
    title: str
    data: dict[str, str]
    reserved: datetime | None
    sent: datetime | None
    read: datetime | None
    error: str


class MessageDetailSchema(MessageSchema):
    body: str


class AppealSchema(TimeStampedMixinSchema):
    id: int
    question_id: int
    explanation: str
    review: str
    closed: datetime | None

    @staticmethod
    def resolve_explanation(obj: Appeal):
        return obj.cleaned_explanation


class AppealCreateSchema(Schema):
    explanation: Annotated[str, Field(min_length=1)]
    app_label: str
    model: str
    question_id: int


class SitePolicySchema(TimeStampedMixinSchema):
    class SitePolicyVersionSchema(TimeStampedMixinSchema):
        id: int
        data_category: dict[str, list[str]]
        body: str
        version: str
        effective_date: datetime

    id: int
    effective_version: SitePolicyVersionSchema
    kind: Literal["terms_of_service", "privacy_policy", "cookie_policy", "marketing_policy", "data_retention_policy"]
    title: str
    description: str
    active: bool
    mandatory: bool
    show_on_join: bool
    priority: int


class PolicyVersionAgreementSchema(RootModel[dict[str, bool]]):
    pass


class ThreadSchema(TimeStampedMixinSchema):
    id: int
    title: str
    description: str
    comment_count: int
    rating_count: int
    rating_avg: float
    closed: bool | None


class ThreadCreateSchema(Schema):
    title: str
    app_label: str
    model: str
    subject_id: str
    description: str


class CommentSchema(TimeStampedMixinSchema):
    id: int
    parent_id: int | None
    writer: OwnerSchema
    comment: str
    pinned: bool
    deleted: bool
    rating: int | None

    @staticmethod
    def resolve_comment(obj: Comment):
        return obj.cleaned_comment


class CommentNestedSchema(CommentSchema):
    children: list[CommentSchema]

    @staticmethod
    def resolve_children(obj: Comment):
        children = obj.children.all()
        # assert children from cache
        sorted_children = sorted(children, key=lambda x: (not x.pinned, x.created))
        return sorted_children[: settings.CHILD_COMMENT_MAX_COUNT]


class CommentSaveSchema(Schema):
    id: Annotated[int, Field(None)]
    comment: Annotated[str, Field(None, min_length=5, max_length=1000)]
    rating: Annotated[float | None, Field(None, ge=1, le=5)]
    parent_id: Annotated[int | None, Field(None)]

    @model_validator(mode="after")
    def validate_id_or_comment(self):
        if not (self.id or self.comment):
            raise ValueError(ErrorCode.EMPTY_REQUEST)
        return self


class CommentSavedSchema(TimeStampedMixinSchema):
    id: int
    comment: str
    parent_id: int | None
    pinned: bool
    deleted: bool
    rating: int | None

    @staticmethod
    def resolve_comment(obj: Comment):
        return obj.cleaned_comment


class CommentBriefSchema(TimeStampedMixinSchema):
    class CommentThreadSchema(TimeStampedMixinSchema):
        id: int
        subject_type: ContentTypeSchema
        title: str
        subject_id: str

    id: int
    comment_brief: str
    parent_id: int | None
    thread: CommentThreadSchema
    pinned: bool
    deleted: bool
    rating: int | None
