from datetime import timedelta
from typing import TYPE_CHECKING, NotRequired, Sequence, TypedDict, cast

import pghistory
from celery.exceptions import ImproperlyConfigured
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.signing import dumps
from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    Count,
    F,
    ForeignKey,
    Index,
    JSONField,
    Model,
    OneToOneField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    TextField,
    UniqueConstraint,
)
from django.db.models.fields import BooleanField, DateTimeField
from django.db.models.functions import Length
from django.db.models.query import Prefetch
from django.db.utils import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pghistory.models import PghEventModel

from apps.account.models import OtpLog
from apps.common.error import ErrorCode
from apps.common.models import GradeFieldMixin, GradeWorkflowMixin, LearningObjectMixin, TimeStampedMixin
from apps.common.util import AccessDate, GradingDate, LearningSessionStep, OtpTokenDict, ScoreStatsDict, get_score_stats
from apps.operation.models import Appeal, AttachmentMixin, HonorCode

User = get_user_model()

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser as User


class SessionDict(TypedDict):
    access_date: AccessDate
    grading_date: GradingDate
    step: LearningSessionStep
    discussion: "Discussion"
    attempt: NotRequired["Attempt"]
    post_count: NotRequired["PostCountDict"]
    grade: NotRequired["Grade"]
    appeal: NotRequired["Appeal"]
    stats: NotRequired[ScoreStatsDict]
    otp_token: NotRequired[str]


class PostCountDict(TypedDict):
    post: int
    reply: int
    valid_post: int
    valid_reply: int


@pghistory.track()
class QuestionPool(Model):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), blank=True, default="")
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"), related_name="+")

    class Meta:
        verbose_name = _("Question Pool")
        verbose_name_plural = _("Question Pools")
        constraints = [UniqueConstraint(fields=["title", "owner"], name="discussion_questionpool_ti_ow_uniq")]

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    async def select_question(self):
        question = await self.question_set.order_by("?").afirst()
        if not question:
            raise ImproperlyConfigured("QuestionPool is empty")

        return question


@pghistory.track()
class Question(Model):
    pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))
    directive = TextField(_("Directive"))
    supplement = TextField(_("Supplement"), blank=True, default="")
    point_requirements = JSONField(_("Point Requirements"))

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    @property
    def post_point(self):
        return self.point_requirements.get("post", 1)

    @property
    def reply_point(self):
        return self.point_requirements.get("reply", 1)

    @property
    def tutor_assessment_point(self):
        return self.point_requirements.get("tutor_assessment", 1)

    @property
    def point(self):
        return self.post_point + self.reply_point + self.tutor_assessment_point

    @property
    def post_min_characters(self):
        return self.point_requirements.get("post_min_characters", 200)

    @property
    def reply_min_characters(self):
        return self.point_requirements.get("reply_min_characters", 100)


@pghistory.track()
class Discussion(LearningObjectMixin, GradeWorkflowMixin):
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    honor_code = ForeignKey(HonorCode, CASCADE, verbose_name=_("Honor Code"))
    question_pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))

    class Meta(LearningObjectMixin.Meta, GradeWorkflowMixin.Meta):
        verbose_name = _("Discussion")
        verbose_name_plural = _("Discussions")
        constraints = [UniqueConstraint(fields=["owner", "title"], name="discussion_ow_ti_uniq")]

    if TYPE_CHECKING:
        question_pool_id: int
        pk: str

    @classmethod
    async def get_session(cls, *, discussion_id: str, learner_id: str, context: str, access_date: AccessDate):
        discussion = await Discussion.objects.select_related("owner", "honor_code", "question_pool").aget(
            id=discussion_id
        )
        session = SessionDict(
            access_date=access_date,
            grading_date=discussion.get_grading_date(access_date),
            step=LearningSessionStep.READY,
            discussion=discussion,
        )

        attempt = (
            await Attempt.objects
            .filter(discussion_id=discussion_id, learner_id=learner_id, context=context, active=True)
            .select_related("discussion", "grade", "question")
            .alast()
        )

        if not attempt:
            if discussion.verification_required:
                session["otp_token"] = dumps(
                    OtpTokenDict(
                        consumer_id=discussion.pk, app_label="discussion", model="discussion", user_id=learner_id
                    )
                )
            return session

        session["attempt"] = attempt
        session["post_count"] = await attempt.post_count()
        session["step"] = LearningSessionStep.SITTING

        if not hasattr(attempt, "grade") or not attempt.grade.completed:
            # still SITTING
            # cf. Assignment.get_session, Exam.get_session
            return session

        session["grade"] = attempt.grade

        try:
            session["appeal"] = await Appeal.objects.prefetch_related("attachments").aget(
                question_id=attempt.question_id, learner_id=learner_id
            )
        except Appeal.DoesNotExist:
            pass

        if not attempt.grade.confirmed:
            session["step"] = LearningSessionStep.REVIEWING
            return session

        session["stats"] = await get_score_stats(
            base_model=Discussion, base_model_id=discussion_id, grade_model=Grade, attempt_model=Attempt
        )
        session["step"] = LearningSessionStep.FINAL

        return session


@pghistory.track()
class Attempt(Model):
    discussion = ForeignKey(Discussion, CASCADE, verbose_name=_("Discussion"))
    learner = ForeignKey(User, CASCADE, verbose_name=_("Learner"), related_name="+")
    question = ForeignKey(Question, CASCADE, verbose_name=_("Question"))
    started = DateTimeField(_("Attempt Start"))
    active = BooleanField(_("Active"), default=True)
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta:
        verbose_name = _("Attempt")
        verbose_name_plural = _("Attempts")
        indexes = [Index(fields=["learner_id", "active"])]
        constraints = [
            UniqueConstraint(
                fields=["discussion", "learner", "context"],
                condition=Q(active=True),
                name="discussion_attemp_di_le_co_ke_uniq",
            )
        ]

    if TYPE_CHECKING:
        learner_id: str
        question_id: int
        post_set: "QuerySet[Post]"
        max_attempts: int  # annotated

    @classmethod
    async def start(cls, *, discussion_id: str, learner_id: str, context: str):
        discussion = await Discussion.objects.aget(id=discussion_id)

        if discussion.verification_required:
            if not await OtpLog.check_otp_verification(user_id=learner_id, consumer=discussion):
                raise ValueError(ErrorCode.OTP_VERIFICATION_REQUIRED)

        question = await QuestionPool(id=discussion.question_pool_id).select_question()

        try:
            attempt = await Attempt.objects.acreate(
                discussion=discussion,
                learner_id=learner_id,
                context=context,
                active=True,
                started=timezone.now() + timedelta(seconds=1),
                question=question,
            )
        except IntegrityError:
            raise ValueError(ErrorCode.ATTEMPT_ALREADY_STARTED)

        # preliminary grade
        await Grade(attempt=attempt).grade()

        return attempt

    @classmethod
    async def deactivate(cls, *, discussion_id: str, learner_id: str, context: str):
        qs = cls.objects.filter(discussion_id=discussion_id, learner_id=learner_id, context=context)
        attempt = await qs.annotate(max_attempts=F("discussion__max_attempts")).aget(active=True)
        total_count = await qs.acount()

        if attempt.max_attempts and attempt.max_attempts <= total_count:
            raise ValueError(ErrorCode.MAX_ATTEMPTS_REACHED)

        attempt.active = False
        await attempt.asave()

    @classmethod
    def get_posts(cls, *, discussion_id: str, learner_id: str, context: str):
        ranked_children = (
            Post.objects
            .filter(parent_id=OuterRef("parent_id"))
            .order_by("id")
            .values("id")[: settings.CHILD_POST_MAX_COUNT]
        )
        return (
            Post.objects
            .select_related("attempt__learner")
            .prefetch_related(
                "attachments",
                Prefetch(
                    "children",
                    queryset=Post.objects
                    .filter(id__in=Subquery(ranked_children))
                    .select_related("attempt__learner")
                    .prefetch_related("attachments")
                    .order_by("id"),
                ),
            )
            .filter(
                attempt__discussion_id=discussion_id,
                attempt__learner_id=learner_id,
                attempt__context=context,
                attempt__active=True,
                parent__isnull=True,
            )
            .order_by("-id")
        )

    async def post_count(self):
        q = self.question
        counts = await self.post_set.annotate(body_len=Length("body")).aaggregate(
            post=Count("pk", filter=Q(parent__isnull=True)),
            reply=Count("pk", filter=Q(parent__isnull=False)),
            valid_post=Count("pk", filter=Q(parent__isnull=True, body_len__gte=q.post_min_characters)),
            valid_reply=Count(
                "pk",
                filter=Q(parent__isnull=False, body_len__gte=q.reply_min_characters)
                & ~Q(parent__attempt__learner_id=self.learner_id),
            ),
        )
        return cast(PostCountDict, counts)


@pghistory.track()
class Post(TimeStampedMixin, AttachmentMixin):
    attempt = ForeignKey(Attempt, CASCADE, verbose_name=_("Attempt"))
    parent = ForeignKey("self", CASCADE, null=True, blank=True, related_name="children", verbose_name=_("Parent"))
    title = CharField(_("Title"), max_length=255)
    body = TextField(_("Body"))

    class Meta(TimeStampedMixin.Meta, AttachmentMixin.Meta):
        verbose_name = _("Post")
        verbose_name_plural = _("Posts")

    if TYPE_CHECKING:
        pk: int
        child_count: int  # annotated
        post_count: "PostCountDict"

    @property
    def cleaned_body(self):
        return self.update_attachment_urls(content=self.body)

    @classmethod
    async def create(
        cls,
        *,
        discussion_id: str,
        learner_id: str,
        context: str,
        parent_id: int | None,
        title: str,
        body: str,
        files: Sequence[File] | None,
    ):
        attempt = await Attempt.objects.select_related("learner", "question").aget(
            discussion_id=discussion_id, learner_id=learner_id, context=context, active=True
        )
        post = await Post.objects.acreate(attempt=attempt, title=title, parent_id=parent_id, body=body)
        await post.update_attachments(files=files, owner_id=learner_id, content=post.body)
        post._state.fields_cache["attempt"] = attempt
        setattr(post, "post_count", await post.attempt.post_count())
        return post

    @classmethod
    async def update(
        cls,
        *,
        discussion_id: str,
        learner_id: str,
        context: str,
        post_id: int,
        title: str,
        body: str,
        files: Sequence[File] | None,
    ):
        post = (
            await Post.objects
            .select_related("attempt__learner")
            .prefetch_related("attachments")
            .aget(
                id=post_id,
                attempt__discussion_id=discussion_id,
                attempt__learner_id=learner_id,
                attempt__context=context,
                attempt__active=True,
            )
        )
        post.title = title
        post.body = body
        await post.asave()
        await post.update_attachments(files=files, owner_id=learner_id, content=post.body)
        return post

    @classmethod
    async def remove(cls, *, discussion_id: str, learner_id: str, context: str, post_id: int):
        post = (
            await Post.objects
            .annotate(child_count=Count("children"))
            .filter(
                id=post_id,
                attempt__discussion_id=discussion_id,
                attempt__learner_id=learner_id,
                attempt__context=context,
                attempt__active=True,
            )
            .aget()
        )

        if post.child_count > 0:
            raise ValueError(ErrorCode.CHILDREN_EXISTS)

        await post.adelete()


@pghistory.track()
class Grade(GradeFieldMixin, TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    grader = ForeignKey(User, SET_NULL, null=True, blank=True, verbose_name=_("Grader"), related_name="+")

    class Meta(TimeStampedMixin.Meta, GradeFieldMixin.Meta):
        verbose_name = _("Grade")
        verbose_name_plural = _("Grades")

    if TYPE_CHECKING:
        pk: int
        pgh_event_model: PghEventModel

    async def grade(self, grader: "User | None" = None):
        question = self.attempt.question
        post_count = await self.attempt.post_count()

        # existing grade
        tutor_assessment_point = (self.earned_details or {}).get("tutor_assessment", 0)

        # update grade
        self.earned_details = {
            "post": min(post_count["valid_post"], question.post_point),
            "reply": min(post_count["valid_reply"], question.reply_point),
            "tutor_assessment": min(tutor_assessment_point, question.tutor_assessment_point),
        }

        self.possible_point = question.point
        self.earned_point = sum(self.earned_details.values())
        self.score = self.earned_point * 100.0 / self.possible_point if self.possible_point else 0.0
        self.passed = self.score >= (self.attempt.discussion.passing_point or 0)
        self.grader_id = grader.pk if grader else None

        await self.asave()
