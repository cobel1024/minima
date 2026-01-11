import random
from typing import TYPE_CHECKING

import pghistory
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKey,
    JSONField,
    ManyToManyField,
    Model,
    OneToOneField,
    PositiveSmallIntegerField,
    Q,
    QuerySet,
    TextField,
    UniqueConstraint,
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import GradeFieldMixin, GradeWorkflowMixin, LearningObjectMixin, TimeStampedMixin

User = get_user_model()


@pghistory.track()
class QuestionPool(Model):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), default="", blank=True)
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"), related_name="+")
    select_count = PositiveSmallIntegerField(_("Select Count"))

    class Meta:
        verbose_name = _("Question Pool")
        verbose_name_plural = _("Question Pools")
        constraints = [UniqueConstraint(fields=["title", "owner"], name="quiz_questionpool_ti_ow_uniq")]

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    def select_questions(self):
        questions = list(self.question_set.all())
        count = min(self.select_count, len(questions))
        return random.sample(questions, count)


@pghistory.track()
class Question(Model):
    pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))
    question = TextField(_("Question"))
    supplement = TextField(_("Supplement"), blank=True, default="")
    options = ArrayField(TextField(), verbose_name=_("Options"))
    point = PositiveSmallIntegerField(_("Point"), default=1)

    class Meta:
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    if TYPE_CHECKING:
        pk: int
        solution: "Solution"


@pghistory.track()
class Solution(Model):
    question = OneToOneField(Question, CASCADE, verbose_name=_("Question"))
    correct_answers = ArrayField(CharField(max_length=50), blank=True, default=list, verbose_name=_("Correct Answers"))
    explanation = TextField(_("Explanation"), blank=True, default="")

    class Meta:
        verbose_name = _("Solution")
        verbose_name_plural = _("Solutions")


@pghistory.track()
class Quiz(LearningObjectMixin):
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    question_pool = ForeignKey(QuestionPool, CASCADE, verbose_name=_("Question Pool"))

    class Meta(LearningObjectMixin.Meta, GradeWorkflowMixin.Meta):
        verbose_name = _("Quiz")
        verbose_name_plural = _("Quizzes")
        constraints = [UniqueConstraint(fields=["owner", "title"], name="quiz_quiz_ow_ti_uniq")]


@pghistory.track()
class Attempt(TimeStampedMixin):
    quiz = ForeignKey(Quiz, CASCADE, verbose_name=_("Quiz"))
    learner = ForeignKey(User, CASCADE, verbose_name=_("Learner"), related_name="+")
    started = DateTimeField(_("Attempt Start"))
    questions = ManyToManyField(Question, verbose_name=_("Questions"))
    active = BooleanField(_("Active"), default=True)
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Attempt")
        verbose_name_plural = _("Attempts")
        constraints = [
            UniqueConstraint(
                fields=["quiz", "learner", "context"], condition=Q(active=True), name="quiz_attemp_qu_le_co_ke_uniq"
            )
        ]

    if TYPE_CHECKING:
        learner_id: str
        submission: "Submission"


@pghistory.track()
class Submission(TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))
    answers = JSONField(_("Answers"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Submission")
        verbose_name_plural = _("Submissions")


@pghistory.track()
class Grade(GradeFieldMixin, TimeStampedMixin):
    attempt = OneToOneField(Attempt, CASCADE, verbose_name=_("Attempt"))

    class Meta(GradeFieldMixin.Meta, TimeStampedMixin.Meta):
        verbose_name = _("Grade")
        verbose_name_plural = _("Grades")

    if TYPE_CHECKING:
        pk: int

    def grade(self):
        questions = list(self.attempt.questions.select_related("solution").order_by("id"))
        if not questions:
            raise ValueError("No question found")

        correct_answer_dict: dict[str, list[str]] = {}
        point_dict: dict[str, int] = {}

        if not self.earned_details:
            self.earned_details = {}

        for q in questions:
            if q.solution.correct_answers:
                correct_answer_dict[str(q.pk)] = q.solution.correct_answers
            point_dict[str(q.pk)] = q.point

        for q_id_str, answer in self.attempt.submission.answers.items():
            if q_id_str in correct_answer_dict:
                is_correct = answer in correct_answer_dict[q_id_str]
                self.earned_details[q_id_str] = point_dict[q_id_str] if is_correct else 0
            else:
                self.earned_details.setdefault(q_id_str, None)

        self.possible_point = sum(point_dict.values())
        self.earned_point = sum(filter(None, self.earned_details.values()))
        self.score = self.earned_point * 100.0 / self.possible_point if self.possible_point else 0.0
        self.passed = self.score >= (self.attempt.quiz.passing_point or 0)
        self.completed = timezone.now()
        self.save()
