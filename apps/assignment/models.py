from datetime import timedelta
from typing import TYPE_CHECKING, NotRequired, Sequence, TypedDict

import pghistory
from asgiref.sync import sync_to_async
from bs4 import BeautifulSoup
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.files import File
from django.core.signing import dumps
from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    F,
    FileField,
    FloatField,
    ForeignKey,
    Index,
    Model,
    OneToOneField,
    PositiveSmallIntegerField,
    Q,
    QuerySet,
    TextChoices,
    TextField,
    UniqueConstraint,
)
from django.db.models.fields import BooleanField, DateTimeField
from django.db.utils import IntegrityError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from pghistory.models import PghEventModel
from tika import parser

from apps.account.models import OtpLog
from apps.common.error import ErrorCode
from apps.common.models import GradeFieldMixin, GradeWorkflowMixin, LearningObjectMixin, TimeStampedMixin
from apps.common.util import AccessDate, GradingDate, LearningSessionStep, OtpTokenDict, ScoreStatsDict, get_score_stats
from apps.operation.models import Appeal, AttachmentMixin, HonorCode

User = get_user_model()

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser as User


class PlagiarismDetectedException(ValueError):
    pass


class SessionDict(TypedDict):
    access_date: AccessDate
    grading_date: GradingDate
    step: LearningSessionStep
    assignment: "Assignment"
    attempt: NotRequired["Attempt"]
    submission: NotRequired["Submission"]
    grade: NotRequired["Grade"]
    appeal: NotRequired["Appeal"]
    analysis: NotRequired["dict[str, dict[str, int]]"]
    stats: NotRequired[ScoreStatsDict]
    otp_token: NotRequired[str]


@pghistory.track()
class QuestionPool(Model):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), blank=True, default="")
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"), related_name="+")

    class Meta:
        verbose_name = _("Question Pool")
        verbose_name_plural = _("Question Pools")
        constraints = [UniqueConstraint(fields=["title", "owner"], name="assignment_questionpool_ti_ow_uniq")]

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    async def select_question(self):
        question = await self.question_set.select_related("solution__rubric").order_by("?").afirst()
        if not question:
            raise ValueError(ErrorCode.QUESTION_POOL_EMPTY)

        return question


ATTACHMENT_MAX_SIZE_MB = 100


@pghistory.track()
class Question(Model):
    pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))
    question = TextField(_("Question"))
    supplement = TextField(_("Supplement"), blank=True, default="")
    attachment_file_count = PositiveSmallIntegerField(_("Attachment File Count"), default=1)
    attachment_file_types = ArrayField(CharField(max_length=10), blank=True, default=list, verbose_name=_("Attachment File Types"))  # fmt: off
    sample_attachment = FileField(_("Sample Attachment"), blank=True, null=True)
    plagiarism_threshold = PositiveSmallIntegerField(_("Plagiarism Threshold Percentage"))

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    if TYPE_CHECKING:
        solution: "Solution"

    @property
    def sample_attachment_url(self):
        if self.sample_attachment:
            return self.sample_attachment.url


@pghistory.track()
class Solution(Model):
    question = OneToOneField(Question, CASCADE, verbose_name=_("Question"))
    rubric = ForeignKey("Rubric", CASCADE, verbose_name=_("Rubric"))
    explanation = TextField(_("Explanation"), blank=True, default="")
    reference = ArrayField(TextField(), blank=True, default=list, verbose_name=_("Reference"))

    class Meta:
        verbose_name = _("Solution")
        verbose_name_plural = _("Solutions")

    @property
    def rubric_data(self):
        return getattr(self, "_rubric_data", None)

    @rubric_data.setter
    def rubric_data(self, data: RubricDataDict):
        self._rubric_data = data

    async def get_rubric_data(self) -> RubricDataDict:
        levels = [
            level
            async for level in PerformanceLevel.objects
            .filter(criterion__rubric=self.rubric)
            .select_related("criterion")
            .order_by("criterion__id", "point")
            .values("id", "name", "description", "point", "criterion__id", "criterion__name", "criterion__description")
        ]

        criteria_dict = {}
        max_points_by_criterion = {}

        for level in levels:
            criterion_id = level["criterion__id"]

            if criterion_id not in criteria_dict:
                criteria_dict[criterion_id] = {
                    "id": criterion_id,
                    "name": level["criterion__name"],
                    "description": level["criterion__description"],
                    "performance_levels": [],
                }
                max_points_by_criterion[criterion_id] = {"max_point": level["point"]}
            else:
                max_points_by_criterion[criterion_id]["max_point"] = max(
                    max_points_by_criterion[criterion_id]["max_point"], level["point"]
                )

            criteria_dict[criterion_id]["performance_levels"].append({
                "id": level["id"],
                "name": level["name"],
                "description": level["description"],
                "point": level["point"],
            })

        possible_point = sum(data["max_point"] for data in max_points_by_criterion.values())

        return {
            "id": self.rubric.pk,
            "name": self.rubric.name,
            "description": self.rubric.description,
            "possible_point": possible_point,
            "criteria": list(criteria_dict.values()),
        }


@pghistory.track()
class Assignment(LearningObjectMixin, GradeWorkflowMixin):
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    honor_code = ForeignKey(HonorCode, CASCADE, verbose_name=_("Honor Code"))
    question_pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))

    class Meta(LearningObjectMixin.Meta, GradeWorkflowMixin.Meta):
        verbose_name = _("Assignment")
        verbose_name_plural = _("Assignments")
        constraints = [UniqueConstraint(fields=["owner", "title"], name="assignment_assignment_ow_ti_uniq")]

    if TYPE_CHECKING:
        question_pool_id: int
        pk: str

    @classmethod
    async def get_session(cls, *, assignment_id: str, learner_id: str, context: str, access_date: AccessDate):
        assignment = await Assignment.objects.select_related("owner", "honor_code", "question_pool").aget(
            id=assignment_id
        )
        session = SessionDict(
            access_date=access_date,
            grading_date=assignment.get_grading_date(access_date),
            step=LearningSessionStep.READY,
            assignment=assignment,
        )

        attempt = (
            await Attempt.objects
            .filter(assignment_id=assignment_id, learner_id=learner_id, context=context, active=True)
            .select_related("assignment", "submission", "grade", "question__solution__rubric")
            .alast()
        )

        if not attempt:
            if assignment.verification_required:
                session["otp_token"] = dumps(
                    OtpTokenDict(
                        consumer_id=assignment.pk, app_label="assignment", model="assignment", user_id=learner_id
                    )
                )
            return session

        # cf exam solution logic
        attempt.question.solution.rubric_data = await attempt.question.solution.get_rubric_data()
        session["attempt"] = attempt

        if not hasattr(attempt, "submission"):
            session["step"] = LearningSessionStep.SITTING
            return session

        session["submission"] = attempt.submission
        attempt.submission._prefetched_objects_cache = {
            "attachments": [a async for a in attempt.submission.attachments.all()]
        }

        if not hasattr(attempt, "grade") or not attempt.grade.completed:
            session["step"] = LearningSessionStep.GRADING
            return session

        session["grade"] = attempt.grade
        session["analysis"] = await assignment.analyze_answers([attempt.question_id])

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
            base_model=Assignment, base_model_id=assignment_id, grade_model=Grade, attempt_model=Attempt
        )
        session["step"] = LearningSessionStep.FINAL

        return session

    async def analyze_answers(self, question_ids: Sequence[int]):
        from apps.assignment.documents import SubmissionDocument

        return await sync_to_async(SubmissionDocument.analyze_answers)(question_ids=question_ids)


@pghistory.track()
class Attempt(Model):
    assignment = ForeignKey(Assignment, CASCADE, verbose_name=_("Assignment"))
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
                fields=["assignment", "learner", "context"],
                condition=Q(active=True),
                name="assignment_attempt_as_le_co_ke_uniq",
            )
        ]

    if TYPE_CHECKING:
        learner_id: str
        question_id: int
        plagiarism_threshold: int  # annotated
        max_attempts: int  # annotated
        total_count: int  # annotated
        submission: "Submission"

    @classmethod
    async def start(cls, *, assignment_id: str, learner_id: str, context: str):
        assignment = await Assignment.objects.aget(id=assignment_id)

        if assignment.verification_required:
            if not await OtpLog.check_otp_verification(user_id=learner_id, consumer=assignment):
                raise ValueError(ErrorCode.OTP_VERIFICATION_REQUIRED)

        question = await QuestionPool(id=assignment.question_pool_id).select_question()
        question.solution.rubric_data = await question.solution.get_rubric_data()

        try:
            attempt = await Attempt.objects.acreate(
                assignment=assignment,
                learner_id=learner_id,
                context=context,
                active=True,
                started=timezone.now() + timedelta(seconds=1),
                question=question,
            )
        except IntegrityError:
            raise ValueError(ErrorCode.ATTEMPT_ALREADY_STARTED)

        attempt._state.fields_cache["submission"] = None

        return attempt

    @classmethod
    async def submit(
        cls, *, assignment_id: str, learner_id: str, context: str, answer: str, files: Sequence[File] | None
    ):
        attempt = await cls.objects.select_related("assignment", "question__solution__rubric").aget(
            assignment_id=assignment_id, learner_id=learner_id, context=context, active=True
        )

        file_count = attempt.question.attachment_file_count
        if file_count > 0:
            if not files or len(files) < file_count:
                raise ValueError(ErrorCode.ATTACHMENT_TOO_FEW)
            Submission.validate_files(
                files, max_count=attempt.question.attachment_file_count, max_size=ATTACHMENT_MAX_SIZE_MB * 1024 * 1024
            )

        content = BeautifulSoup(answer, "html.parser").get_text(separator=" ", strip=True)
        for f in files or []:
            tika_response = parser.from_buffer(f, settings.TIKA_HOST)
            content += "\n" + (tika_response.get("content") or "").strip()

        if not content:
            raise ValueError(ErrorCode.EMPTY_ANSWER)

        # pretest plagiarism
        if attempt.question.plagiarism_threshold > 0:
            from apps.assignment.documents import SubmissionDocument

            test_result = await sync_to_async(SubmissionDocument.check_similarity)(
                question_id=attempt.question_id, user_id=learner_id, text=content
            )

            similarity_percentage = test_result["similarity_percentage"]
            if similarity_percentage >= attempt.question.plagiarism_threshold:
                raise PlagiarismDetectedException([ErrorCode.PLAGIARISM_DETECTED, similarity_percentage])

        submission = await Submission.create(attempt=attempt, answer=answer, extracted_text=content, files=files)

        # preliminary grade
        await submission.create_preliminary_grade()

        return submission

    @classmethod
    async def deactivate(cls, *, assignment_id: str, learner_id: str, context: str):
        qs = cls.objects.filter(assignment_id=assignment_id, learner_id=learner_id, context=context)
        attempt = await qs.annotate(max_attempts=F("assignment__max_attempts")).aget(active=True)
        total_count = await qs.acount()

        if attempt.max_attempts and attempt.max_attempts <= total_count:
            raise ValueError(ErrorCode.MAX_ATTEMPTS_REACHED)

        attempt.active = False
        await attempt.asave()


@pghistory.track()
class Submission(TimeStampedMixin, AttachmentMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    answer = TextField(_("Answer"))
    extracted_text = TextField(_("Extracted Text"), blank=True, default="")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Submission")
        verbose_name_plural = _("Submissions")

    if TYPE_CHECKING:
        pgh_event_model: PghEventModel

    @property
    def cleaned_answer(self):
        return self.update_attachment_urls(content=self.answer)

    async def create_preliminary_grade(self):
        await Grade(attempt=self.attempt).grade()

    @classmethod
    async def create(cls, *, attempt: "Attempt", answer: str, extracted_text: str, files: Sequence[File] | None):
        submission, created = await Submission.objects.aget_or_create(
            attempt=attempt, defaults={"answer": answer, "extracted_text": extracted_text}
        )

        if not created:
            raise ValueError(ErrorCode.ATTEMPT_ALREADY_SUBMITTED)

        await submission.update_attachments(files=files, owner_id=attempt.learner_id, content=submission.answer)
        return submission


@pghistory.track()
class Grade(GradeFieldMixin, TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    grader = ForeignKey(User, SET_NULL, null=True, blank=True, verbose_name=_("Grader"), related_name="+")

    class Meta(GradeFieldMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("Grade")
        verbose_name_plural = _("Grades")

    if TYPE_CHECKING:
        pk: int
        attempt_id: int
        pgh_event_model: PghEventModel

    async def grade(self, grader: "User | None" = None):
        rubric_data = await self.attempt.question.solution.get_rubric_data()
        default_details = {criterion["name"]: None for criterion in rubric_data["criteria"]}
        self.earned_details = default_details | (self.earned_details or {})
        self.possible_point = rubric_data["possible_point"]
        self.earned_point = sum(filter(None, self.earned_details.values()))
        self.score = (self.earned_point * 100.0 / self.possible_point) if self.possible_point else 0
        self.passed = self.score >= (self.attempt.assignment.passing_point or 0)
        self.grader_id = grader.pk if grader else None
        await self.asave()


@pghistory.track()
class PlagiarismCheck(TimeStampedMixin):
    class StatusChoices(TextChoices):
        NOT_DETECTED = "not_detected", _("Not Detected")
        DETECTED = "detected", _("Detected")
        EXCUSED = "excused", _("Excused")
        NOT_RESOLVED = "not_resolved", _("Not Resolved")

    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    status = CharField(_("Status"), max_length=20, choices=StatusChoices.choices, db_index=True)
    similarity_percentage = FloatField(_("Similarity Percentage"))
    flagged_text = TextField(_("Flagged Text"))
    source_text = TextField(_("Source Text"))
    source_user_id = CharField(_("Source User ID"), max_length=36)
    reason = TextField(_("Reason"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Plagiarism Check")
        verbose_name_plural = _("Plagiarism Checks")


class RubricDataDict(TypedDict):
    id: int
    name: str
    description: str
    possible_point: int
    criteria: "list[RubricCriterionDataDict]"


class RubricCriterionDataDict(TypedDict):
    id: int
    name: str
    description: str
    performance_levels: "list[PerformanceLevelDataDict]"


class PerformanceLevelDataDict(TypedDict):
    id: int
    name: str
    description: str
    point: int


@pghistory.track()
class Rubric(Model):
    name = CharField(_("Name"), max_length=255, unique=True)
    description = TextField(_("Description"))

    class Meta:
        verbose_name = _("Rubric")
        verbose_name_plural = _("Rubrics")

    if TYPE_CHECKING:
        pk: int
        rubriccriterion_set: "QuerySet[RubricCriterion]"

    def __str__(self):
        return self.name


@pghistory.track()
class RubricCriterion(Model):
    rubric = ForeignKey(Rubric, CASCADE, verbose_name=_("Rubric"))
    name = CharField(_("Name"), max_length=255)
    description = TextField(_("Description"))

    class Meta:
        verbose_name = _("Rubric Criterion")
        verbose_name_plural = _("Rubric Criteria")
        constraints = [UniqueConstraint(fields=["rubric", "name"], name="assigment_rubriccriterion_ru_na_uniq")]

    if TYPE_CHECKING:
        pk: int
        performancelevel_set: "QuerySet[PerformanceLevel]"

    def __str__(self):
        return self.name


@pghistory.track()
class PerformanceLevel(Model):
    criterion = ForeignKey(RubricCriterion, CASCADE, verbose_name=_("Criterion"))
    name = CharField(_("Name"), max_length=255)
    description = TextField(_("Description"))
    point = PositiveSmallIntegerField(_("Point"))

    class Meta:
        verbose_name = _("Performance Level")
        verbose_name_plural = _("Performance Levels")
        constraints = [
            UniqueConstraint(fields=["criterion", "name"], name="assignment_performancelevel_cr_na_uniq"),
            UniqueConstraint(fields=["criterion", "point"], name="assignment_performancelevel_cr_po_uniq"),
        ]

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return self.name
