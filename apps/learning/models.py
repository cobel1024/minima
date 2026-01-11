from collections import defaultdict
from datetime import timedelta
from typing import TYPE_CHECKING

import pghistory
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.aggregates.general import ArrayAgg
from django.db import IntegrityError
from django.db.models import (
    CASCADE,
    SET_NULL,
    BooleanField,
    CharField,
    Count,
    DateTimeField,
    Exists,
    F,
    ForeignKey,
    Index,
    OuterRef,
    Q,
    Subquery,
    TextField,
    UniqueConstraint,
    Value,
)
from django.db.models.functions import Concat, JSONObject
from django.db.models.functions.math import Round
from django.forms import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pghistory.models import PghEventModel

from apps.assignment.models import Assignment
from apps.assignment.models import Grade as AssignmentGrade
from apps.common.error import ErrorCode
from apps.common.models import OrderableMixin, TimeStampedMixin
from apps.common.util import offset_paginate
from apps.content.models import Media, Watch
from apps.course.models import Course, Engagement, Gradebook
from apps.discussion.models import Discussion
from apps.discussion.models import Grade as DiscussionGrade
from apps.exam.models import Exam
from apps.exam.models import Grade as ExamGrade
from apps.learning.trigger import enrollment_content_exists
from apps.quiz.models import Grade as QuizGrade
from apps.quiz.models import Quiz
from apps.survey.models import Survey

User = get_user_model()

ENROLLABLE_MODELS = [Course, Media, Exam, Assignment, Discussion, Survey]
ENROLLABLE_MODEL_MAP = {(m._meta.app_label.lower(), m._meta.model.__name__.lower()): m for m in ENROLLABLE_MODELS}

# cf Course.ASSESSIBLE_GRADE_MODELS
ALL_GRADE_MODELS = {Exam: ExamGrade, Assignment: AssignmentGrade, Discussion: DiscussionGrade, Quiz: QuizGrade}


@pghistory.track()
class Enrollment(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    active = BooleanField(_("Active"), default=True)
    start = DateTimeField(_("Start"), default=timezone.now)
    end = DateTimeField(_("End"))
    archive = DateTimeField(_("Archive"))
    enrolled = DateTimeField(_("Enrolled"), auto_now_add=True)
    content_type = ForeignKey(
        ContentType,
        CASCADE,
        verbose_name=_("Content Type"),
        limit_choices_to={"model__in": [m.__name__.lower() for m in ENROLLABLE_MODELS]},
    )
    content_id = CharField(_("Content ID"), max_length=36)
    content = GenericForeignKey("content_type", "content_id")
    enrolled_by = ForeignKey(User, on_delete=SET_NULL, verbose_name=_("Enrolled By"), null=True, related_name="+")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Enrollment")
        verbose_name_plural = _("Enrollments")
        indexes = [
            Index(fields=["user", "content_id", "active"]),
            Index(fields=["enrolled"]),
            Index(fields=["content_id"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["user", "content_type", "content_id"],
                condition=Q(active=True),
                name="enrollment_enrollment_us_itty_itid_uniq",
            )
        ]

    if TYPE_CHECKING:
        content_type_id: int
        pgh_event_model: PghEventModel
        _content_cache: GenericForeignKey
        enrolled_by_id: str
        user_id: str

    @property
    def can_deactivate(self):
        return self.active and self.enrolled_by_id == self.user_id

    def clean(self):
        if self.content_type_id and self.content_id:
            model_class = self.content_type.model_class()
            if not model_class or not model_class.objects.filter(id=self.content_id).exists():
                raise ValidationError(_("Content does not exist"))

    @classmethod
    async def get_enrolled(cls, *, user_id: str, page: int, size: int):
        base_qs = cls.objects.select_related("content_type").filter(user_id=user_id, active=True).order_by("-enrolled")
        paginated = await offset_paginate(base_qs, page=page, size=size)

        if not paginated["items"]:
            return paginated

        content_ids = defaultdict(set)
        for enrollment in paginated["items"]:
            content_ids[(enrollment.content_type.app_label, enrollment.content_type.model)].add(enrollment.content_id)

        contents = await _fetch_enrollable_contents(content_ids)
        await _attach_contents(paginated["items"], contents)

        return paginated

    @classmethod
    async def get_records(cls, user_id: str):
        # Asserted content_id is actually unique

        # to exclude inactive course engagements
        # this makes contect_key unique in course engagement
        active_course_keys = Engagement.objects.filter(learner_id=user_id, active=True).values_list(
            Concat(Value("course::"), F("course_id"), Value("::"), F("pk"), output_field=CharField())
        )

        qs = (
            # media
            Watch.objects
            .filter(
                Q(~Q(context__startswith="course::")) | Q(context__in=Subquery(active_course_keys)), user_id=user_id
            )
            .annotate(rate_=Round("rate", 2))
            .values_list("media_id", "context", "rate_")
        )

        for M, G in ALL_GRADE_MODELS.items():
            pk_path = f"attempt__{M._meta.model.__name__.lower()}_id"
            qs = qs.union(
                G.objects
                .annotate(score_=Round("score", 2))
                .filter(
                    Q(~Q(attempt__context__startswith="course::"))
                    | Q(attempt__context__in=Subquery(active_course_keys)),
                    attempt__learner_id=user_id,
                    attempt__active=True,
                    completed__isnull=False,
                    confirmed__isnull=False,
                )
                .values_list(pk_path, "attempt__context", "score_"),
                all=True,
            )

        # content_id, context, rate or score
        records: dict[str, dict[str, float]] = {}
        async for record in qs:
            content_id, context, value = record

            if context.startswith("course"):
                # cf learning.api.access_control.active_context
                # Frontend only accesses active context, so we can safely normalize
                # Active contexts are unique per user (only one active engagement per course)
                # This simplifies the frontend by removing engagement-specific details
                context = Course.normalize_context(context)

            # another context ...
            if content_id not in records:
                records[content_id] = {}
            records[content_id][context] = value

        enrollments = [
            e
            async for e in Enrollment.objects
            .filter(user_id=user_id, active=True)
            .values("content_type__app_label", "content_type__model")
            .annotate(content_ids=ArrayAgg("content_id"))
        ]

        course_ids: list[str] = []

        for enrollment in enrollments:
            app_label = enrollment["content_type__app_label"]
            model = enrollment["content_type__model"]
            M = ENROLLABLE_MODEL_MAP.get((app_label, model), None)

            if M == Course:
                course_ids.extend(enrollment["content_ids"])

        if course_ids:
            # course have rate and score
            course_grades = [
                g
                async for g in Gradebook.objects.filter(
                    engagement__course_id__in=course_ids, engagement__learner_id=user_id, engagement__active=True
                ).values_list("engagement__course_id", "score")
            ]

            for course_id, score in course_grades:
                if course_id not in records:
                    records[course_id] = {}
                records[course_id][""] = score

        return records

    @classmethod
    async def deactivate(cls, *, id: int, user_id: str):
        enrollment = await cls.objects.aget(id=id, user_id=user_id, active=True)
        if not enrollment.can_deactivate:
            raise ValueError(ErrorCode.PERMISSION_DENIED)
        enrollment.active = False
        await enrollment.asave()


setattr(
    Enrollment._meta, "triggers", [enrollment_content_exists(Enrollment._meta.db_table, ContentType._meta.db_table)]
)


@pghistory.track()
class Catalog(TimeStampedMixin):
    name = CharField(_("Name"), max_length=255, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    active = BooleanField(_("Active"), default=True)
    public = BooleanField(_("Public"), default=False)
    available_from = DateTimeField(_("Available From"), default=timezone.now)
    available_until = DateTimeField(_("Available Until"))

    class Meta:
        verbose_name = _("Catalog")
        verbose_name_plural = _("Catalogs")

    if TYPE_CHECKING:
        item_content_type_id: int

    def is_available(self):
        if not self.active:
            return False

        now = timezone.now()
        return self.available_from <= now <= self.available_until

    @classmethod
    def get_catalogs(cls, user_id: str):
        now = timezone.now()
        return (
            cls.objects
            .filter(
                Q(available_from__lte=now, available_until__gte=now, active=True)
                & (Q(public=True) | Q(usercatalog__user_id=user_id))
            )
            .annotate(item_count=Count("catalogitem", distinct=True))
            .distinct()
            .order_by("-id")
        )

    @classmethod
    async def get_items(cls, *, catalog_id: int, user_id: str, page: int, size: int):
        base_qs = (
            CatalogItem.objects
            .select_related("content_type")
            .annotate(
                enrolled=Exists(
                    Enrollment.objects.filter(
                        user_id=user_id,
                        active=True,
                        content_id=OuterRef("content_id"),
                        content_type=OuterRef("content_type"),
                    )
                )
            )
            .filter(catalog_id=catalog_id, catalog__active=True)
            .order_by("ordering", "-id")
        )
        paginated = await offset_paginate(base_qs, page=page, size=size)

        if not paginated["items"]:
            return paginated

        content_ids = defaultdict(set)
        for item in paginated["items"]:
            content_ids[(item.content_type.app_label, item.content_type.model)].add(item.content_id)

        contents = await _fetch_enrollable_contents(content_ids)
        await _attach_contents(paginated["items"], contents)

        return paginated

    @classmethod
    async def enroll_catalog_item(
        cls, *, catalog_id: int, user_id: str, content_id: str, app_label: str, model: str, enrolled_by_id: str
    ):
        now = timezone.now()
        catalog = (
            await Catalog.objects
            .filter(id=catalog_id, available_from__lte=now, available_until__gte=now, active=True)
            .filter(
                Q(public=True)
                | (
                    Q(usercatalog__user_id=user_id)
                    & Q(
                        catalogitem__content_id=content_id,
                        catalogitem__content_type__app_label=app_label,
                        catalogitem__content_type__model=model,
                    )
                )
            )
            .annotate(
                item_content_type_id=Subquery(
                    ContentType.objects.filter(app_label=app_label, model=model).values("id")[:1]
                )
            )
            .afirst()
        )

        if not catalog:
            raise ValueError(ErrorCode.ACCESS_DENIED)

        try:
            enrollment = await Enrollment.objects.acreate(
                user_id=user_id,
                active=True,
                start=now,
                end=catalog.available_until,
                archive=catalog.available_until + timedelta(days=settings.DEFAULT_REVIEW_PERIOD_DAYS),
                enrolled=now,
                content_type_id=catalog.item_content_type_id,
                content_id=content_id,
                enrolled_by_id=enrolled_by_id,
            )
        except IntegrityError:
            raise ValueError(ErrorCode.ALREADY_EXISTS)

        return enrollment


class CatalogItem(TimeStampedMixin, OrderableMixin):
    catalog = ForeignKey(Catalog, on_delete=CASCADE, verbose_name=_("Catalog"))
    content_type = ForeignKey(
        ContentType,
        CASCADE,
        verbose_name=_("Content Type"),
        limit_choices_to={"model__in": [m.__name__.lower() for m in ENROLLABLE_MODELS]},
    )
    content_id = CharField(_("Content ID"), max_length=36)
    content = GenericForeignKey("content_type", "content_id")

    ordering_group = ("catalog",)

    class Meta:
        verbose_name = _("Catalog Item")
        verbose_name_plural = _("Catalog Items")
        constraints = [
            UniqueConstraint(
                fields=["catalog", "content_type", "content_id"], name="learning_catalogitem_ca_itty_itid_uniq"
            )
        ]

    if TYPE_CHECKING:
        _content_cache: GenericForeignKey


@pghistory.track()
class UserCatalog(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    catalog = ForeignKey(Catalog, on_delete=CASCADE, verbose_name=_("Catalog"))
    granted_by = ForeignKey(User, on_delete=CASCADE, verbose_name=_("Granted By"), null=True, related_name="+")
    note = TextField(_("Note"), blank=True, default="")

    class Meta:
        verbose_name = _("User Catalog")
        verbose_name_plural = _("User Catalogs")
        constraints = [UniqueConstraint(fields=["user", "catalog"], name="learning_usercatalog_us_ca_uniq")]


async def _fetch_enrollable_contents(content_ids_by_type: dict):
    union_qs = []

    for M in ENROLLABLE_MODELS:
        key = (M._meta.app_label.lower(), M._meta.model.__name__.lower())
        ids = content_ids_by_type.get(key)

        if not ids:
            continue

        union_qs.append(
            M.objects
            .filter(id__in=ids)
            .annotate(
                owner_obj=JSONObject(
                    id=F("owner__id"),
                    name=F("owner__name"),
                    email=F("owner__email"),
                    avatar=F("owner__avatar"),
                    nickname=F("owner__nickname"),
                )
            )
            .values(
                "id",
                "created",
                "modified",
                "title",
                "description",
                "audience",
                "thumbnail",
                "featured",
                "format",
                "duration",
                "passing_point",
                "max_attempts",
                "verification_required",
                "owner_obj",
            )
        )

    if not union_qs:
        return {}

    qs = union_qs[0] if len(union_qs) == 1 else union_qs[0].union(*union_qs[1:], all=True)
    return {content["id"]: content async for content in qs}


async def _attach_contents(items, contents):
    for item in items:
        origin_content = contents.get(item.content_id)
        if not origin_content:
            continue

        M = ENROLLABLE_MODEL_MAP.get((item.content_type.app_label, item.content_type.model))
        if not M:
            continue

        content_data = origin_content.copy()
        user = User(**content_data.pop("owner_obj"))
        item._content_cache = M(**content_data, owner=user)


# TODO: !!!!!!!!!!!!!!!!!!!!!!
# class Recommendation(TimeStampedMixin):
