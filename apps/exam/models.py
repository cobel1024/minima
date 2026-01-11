import random
from datetime import timedelta
from typing import TYPE_CHECKING, NotRequired, Sequence, TypedDict

import pghistory
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.signing import dumps
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateTimeField,
    DurationField,
    F,
    ForeignKey,
    Index,
    JSONField,
    ManyToManyField,
    Model,
    OneToOneField,
    PositiveSmallIntegerField,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    TextChoices,
    TextField,
    UniqueConstraint,
)
from django.db.utils import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pghistory.models import PghEventModel

from apps.account.models import OtpLog
from apps.common.error import ErrorCode
from apps.common.models import GradeFieldMixin, GradeWorkflowMixin, LearningObjectMixin, TimeStampedMixin
from apps.common.util import AccessDate, GradingDate, LearningSessionStep, OtpTokenDict, ScoreStatsDict, get_score_stats
from apps.operation.models import Appeal, HonorCode

User = get_user_model()

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser as User


class SessionDict(TypedDict):
    access_date: AccessDate
    grading_date: GradingDate
    step: LearningSessionStep
    exam: "Exam"
    attempt: NotRequired["Attempt"]
    submission: NotRequired["Submission"]
    grade: NotRequired["Grade"]
    solutions: NotRequired["dict[str, Solution]"]
    appeals: NotRequired["dict[str, Appeal]"]
    analysis: NotRequired["dict[str, dict[str, int]]"]
    stats: NotRequired[ScoreStatsDict]
    otp_token: NotRequired[str]


@pghistory.track()
class QuestionPool(Model):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), default="", blank=True)
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"), related_name="+")
    composition = JSONField(_("Question Composition"))

    class Meta:
        verbose_name = _("Question Pool")
        verbose_name_plural = _("Question Pools")
        constraints = [UniqueConstraint(fields=["title", "owner"], name="exam_questionpool_ti_ow_uniq")]

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    async def compose_questions(self):
        all_questions = [q async for q in self.question_set.values_list("id", "format")]
        question_ids = []
        for format, count in self.composition.items():
            ids = [id for id, f in all_questions if f == format]
            random.shuffle(ids)
            question_ids.extend(sorted(ids[:count], key=lambda id: id))
        return Question.objects.filter(id__in=question_ids)


@pghistory.track()
class Question(Model):
    class FormatChoices(TextChoices):
        SINGLE_CHOICE = "single_choice", _("Single Choice")
        TEXT_INPUT = "text_input", _("Text Input")
        NUMBER_INPUT = "number_input", _("Number Input")
        ESSAY = "essay", _("Essay")

    pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))
    format = CharField(_("Format"), max_length=20, choices=FormatChoices.choices)
    question = TextField(_("Question"))
    supplement = TextField(_("Supplement"), blank=True, default="")
    options = ArrayField(TextField(), blank=True, default=list, verbose_name=_("Options"))
    point = PositiveSmallIntegerField(_("Point"), default=1)

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    if TYPE_CHECKING:
        pk: int
        solution: "Solution"

    def __str__(self):
        return f"{self.question[:30]} {'...' if len(self.question) > 30 else ''}"


@pghistory.track()
class Solution(Model):
    question = OneToOneField(Question, CASCADE, verbose_name=_("Question"))
    correct_answers = ArrayField(CharField(max_length=50), blank=True, default=list, verbose_name=_("Correct Answers"))
    correct_criteria = TextField(_("Correct Criteria"), blank=True, default="")
    explanation = TextField(_("Explanation"), blank=True, default="")
    reference = ArrayField(TextField(), blank=True, default=list, verbose_name=_("Reference"))

    class Meta:
        verbose_name = _("Solution")
        verbose_name_plural = _("Solutions")


@pghistory.track()
class Exam(LearningObjectMixin, GradeWorkflowMixin):
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    honor_code = ForeignKey(HonorCode, CASCADE, verbose_name=_("Honor Code"))
    question_pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))
    duration = DurationField(_("Duration"))

    class Meta(LearningObjectMixin.Meta, GradeWorkflowMixin.Meta):
        verbose_name = _("Exam")
        verbose_name_plural = _("Exams")
        constraints = [UniqueConstraint(fields=["owner", "title"], name="exam_exam_ow_ti_uniq")]

    if TYPE_CHECKING:
        question_pool_id: int
        pk: str

    @property
    def duration_seconds(self):
        return self.duration.total_seconds()

    @classmethod
    async def get_session(cls, *, exam_id: str, learner_id: str, context: str, access_date: AccessDate):
        exam = await Exam.objects.select_related("owner", "honor_code", "question_pool").aget(id=exam_id)
        session = SessionDict(
            access_date=access_date,
            grading_date=exam.get_grading_date(access_date),
            step=LearningSessionStep.READY,
            exam=exam,
        )

        attempt = (
            await Attempt.objects
            .filter(exam=exam, learner_id=learner_id, context=context, active=True)
            .select_related("exam", "tempanswer", "submission", "grade")
            .prefetch_related(
                Prefetch("questions", queryset=Question.objects.select_related("solution").order_by("id"))
            )
            .alast()
        )

        if not attempt:
            if exam.verification_required:
                session["otp_token"] = dumps(
                    OtpTokenDict(consumer_id=exam.pk, app_label="exam", model="exam", user_id=learner_id)
                )
            return session

        session["attempt"] = attempt

        if not hasattr(attempt, "submission"):
            if timezone.now() < attempt.started + attempt.exam.duration:
                session["step"] = LearningSessionStep.SITTING
                return session

            session["step"] = LearningSessionStep.TIMEOUT
            return session

        session["submission"] = attempt.submission

        if not hasattr(attempt, "grade") or not attempt.grade.completed:
            session["step"] = LearningSessionStep.GRADING
            return session

        session["grade"] = attempt.grade

        all_questions = attempt.questions.all()
        session["solutions"] = {str(q.pk): q.solution async for q in all_questions if hasattr(q, "solution")}
        session["appeals"] = {
            str(a.question_id): a
            async for a in Appeal.objects.prefetch_related("attachments").filter(
                learner_id=learner_id,
                question_id__in=[q.pk for q in all_questions],
                question_type_id=Subquery(
                    ContentType.objects.filter(model="question", app_label="exam").values("pk")[:1]
                ),
            )
        }
        session["analysis"] = await exam.analyze_answers([q.pk for q in all_questions])

        if not attempt.grade.confirmed:
            session["step"] = LearningSessionStep.REVIEWING
            return session

        session["stats"] = await get_score_stats(
            base_model=Exam, base_model_id=exam_id, grade_model=Grade, attempt_model=Attempt
        )
        session["step"] = LearningSessionStep.FINAL

        return session

    async def analyze_answers(self, question_ids: Sequence[int]):
        from apps.exam.documents import SubmissionDocument

        return await sync_to_async(SubmissionDocument.analyze_answers)(question_ids=question_ids)


@pghistory.track()
class Attempt(Model):
    exam = ForeignKey(Exam, CASCADE, verbose_name=_("Exam"))
    learner = ForeignKey(User, CASCADE, verbose_name=_("Learner"), related_name="+")
    questions = ManyToManyField(Question, verbose_name=_("Questions"))
    started = DateTimeField(_("Attempt Start"))
    active = BooleanField(_("Active"), default=True)
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta:
        verbose_name = _("Attempt")
        verbose_name_plural = _("Attempts")
        indexes = [Index(fields=["learner_id", "active"])]
        constraints = [
            UniqueConstraint(
                fields=["exam", "learner", "context"], condition=Q(active=True), name="exam_attemp_ex_le_co_ke_uniq"
            )
        ]

    if TYPE_CHECKING:
        learner_id: str
        submission: "Submission"
        tempanswer: "TempAnswer"
        total_count: int  # annotated
        max_attempts: int  # annotated
        _prefetched_objects_cache: dict[str, QuerySet[Question]]

    @property
    def saved_answers(self):
        if hasattr(self, "tempanswer") and self.tempanswer:
            return self.tempanswer.answers

    @classmethod
    async def start(cls, *, exam_id: str, learner_id: str, context: str):
        exam = await Exam.objects.prefetch_related("question_pool__question_set").aget(id=exam_id)

        if exam.verification_required:
            if not await OtpLog.check_otp_verification(user_id=learner_id, consumer=exam):
                raise ValueError(ErrorCode.OTP_VERIFICATION_REQUIRED)

        questions = await exam.question_pool.compose_questions()

        try:
            attempt = await Attempt.objects.acreate(
                exam=exam,
                learner_id=learner_id,
                context=context,
                active=True,
                started=timezone.now() + timedelta(seconds=1),
            )
        except IntegrityError:
            raise ValueError(ErrorCode.ATTEMPT_ALREADY_STARTED)

        await attempt.questions.aset(questions)

        attempt._prefetched_objects_cache = {"questions": questions}
        attempt._state.fields_cache["submission"] = None
        attempt._state.fields_cache["tempanswer"] = None

        return attempt

    def _check_can_submit(self):
        if timezone.now() > self.started + self.exam.duration + timedelta(seconds=settings.SUBMISSION_GRACE_PERIOD):
            raise ValueError(ErrorCode.ATTEMPT_HAS_EXPIRED)

    @classmethod
    async def submit(cls, *, exam_id: str, learner_id: str, context: str, answers: dict):
        if not answers:
            raise ValueError(ErrorCode.NO_ANSWERS)

        attempt = (
            await cls.objects
            .select_related("exam")
            .prefetch_related("questions__solution")
            .aget(exam_id=exam_id, learner_id=learner_id, context=context, active=True)
        )

        attempt._check_can_submit()

        try:
            submission = await Submission.objects.acreate(attempt=attempt, answers=answers)
        except IntegrityError:
            raise ValueError(ErrorCode.ATTEMPT_ALREADY_SUBMITTED)

        # preliminary grade
        await submission.create_preliminary_grade()

        return submission

    @classmethod
    async def deactivate(cls, *, exam_id: str, learner_id: str, context: str):
        qs = cls.objects.filter(exam_id=exam_id, learner_id=learner_id, context=context)
        attempt = await qs.annotate(max_attempts=F("exam__max_attempts")).aget(active=True)
        total_count = await qs.acount()

        if attempt.max_attempts and attempt.max_attempts <= total_count:
            raise ValueError(ErrorCode.MAX_ATTEMPTS_REACHED)

        attempt.active = False
        await attempt.asave()

    @classmethod
    async def save_answers(cls, *, exam_id: str, learner_id: str, context: str, answers: dict[str, str]):
        if not answers:
            raise ValueError(ErrorCode.NO_ANSWERS)

        attempt = await cls.objects.select_related("exam").aget(
            exam_id=exam_id, learner_id=learner_id, context=context, active=True
        )
        attempt._check_can_submit()

        # merge answers to existing tempanswer
        temp_answer, created = await TempAnswer.objects.aget_or_create(attempt=attempt, defaults={"answers": answers})

        if not created:
            temp_answer.answers.update(answers)
            await temp_answer.asave(update_fields=["answers"])


@pghistory.track()
class TempAnswer(TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    answers = JSONField(_("Answers"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Temporary Answer")
        verbose_name_plural = _("Temporary Answers")


@pghistory.track()
class Submission(TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    answers = JSONField(_("Answers"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Submission")
        verbose_name_plural = _("Submissions")

    if TYPE_CHECKING:
        pgh_event_model: PghEventModel

    async def create_preliminary_grade(self):
        await Grade(attempt=self.attempt).grade()


@pghistory.track()
class Grade(GradeFieldMixin, TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    grader = ForeignKey(User, CASCADE, null=True, blank=True, verbose_name=_("Grader"), related_name="+")

    class Meta(GradeFieldMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("Grade")
        verbose_name_plural = _("Grades")

    if TYPE_CHECKING:
        pk: int
        pgh_event_model: PghEventModel

    async def grade(self, earned_existing: dict[str, int | None] | None = None, grader: User | None = None):
        questions = [q async for q in self.attempt.questions.select_related("solution").order_by("id")]
        if not questions:
            raise ValueError(ErrorCode.NO_QUESTION)

        correct_answer_dict: dict[str, list[str]] = {}
        point_dict: dict[str, int] = {}

        if not self.earned_details:
            self.earned_details = {}

        for q in questions:
            if hasattr(q, "solution") and q.solution.correct_answers:
                correct_answer_dict[str(q.pk)] = q.solution.correct_answers
            point_dict[str(q.pk)] = q.point

        for q_id_str, answer in self.attempt.submission.answers.items():
            if q_id_str in correct_answer_dict:
                is_correct = answer in correct_answer_dict[q_id_str]
                if not is_correct:
                    for correct in correct_answer_dict[q_id_str]:
                        try:
                            if float(correct) == float(answer):
                                is_correct = True
                                break
                        except ValueError, TypeError:
                            pass
                self.earned_details[q_id_str] = point_dict[q_id_str] if is_correct else 0
            else:
                self.earned_details.setdefault(q_id_str, None)

        if earned_existing is not None:
            self.earned_details.update(earned_existing)

        self.possible_point = sum(point_dict.values())
        self.earned_point = sum(filter(None, self.earned_details.values()))
        self.score = self.earned_point * 100.0 / self.possible_point if self.possible_point else 0.0
        self.passed = self.score >= (self.attempt.exam.passing_point or 0)
        self.grader_id = grader.pk if grader else None
        await self.asave()
