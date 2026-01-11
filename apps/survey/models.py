import hashlib
from typing import TYPE_CHECKING

import pghistory
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    CASCADE,
    SET_NULL,
    BooleanField,
    CharField,
    ForeignKey,
    JSONField,
    Model,
    Q,
    QuerySet,
    TextChoices,
    TextField,
    UniqueConstraint,
)
from django.db.models.indexes import Index
from django.utils.translation import gettext_lazy as _

from apps.common.models import LearningObjectMixin, OrderableMixin, TimeStampedMixin

User = get_user_model()


@pghistory.track()
class QuestionPaper(Model):
    title = CharField(_("Title"), max_length=255)
    description = TextField(_("Description"), default="", blank=True)
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"), related_name="+")

    class Meta:
        verbose_name = _("Question Paper")
        verbose_name_plural = _("Question Papers")
        constraints = [UniqueConstraint(fields=["title", "owner"], name="survey_questionpaper_ti_ow_uniq")]

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"


@pghistory.track()
class Question(OrderableMixin):
    class FormatChoices(TextChoices):
        SINGLE_CHOICE = "single_choice", _("Single Choice")
        TEXT_INPUT = "text_input", _("Text Input")
        NUMBER_INPUT = "number_input", _("Number Input")

    paper = ForeignKey(QuestionPaper, CASCADE, verbose_name=_("Question Paper"))
    format = CharField(_("Format"), max_length=20, choices=FormatChoices.choices)
    question = TextField(_("Question"))
    supplement = TextField(_("Supplement"), blank=True, default="")
    options = ArrayField(TextField(), blank=True, default=list, verbose_name=_("Options"))
    mandatory = BooleanField(_("Mandatory"), default=True)

    ordering_group = ("paper",)

    class Meta(OrderableMixin.Meta):
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")


@pghistory.track()
class Survey(LearningObjectMixin):
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    paper = ForeignKey(QuestionPaper, CASCADE, verbose_name=_("Question Paper"))
    complete_message = TextField(_("Complete Message"), blank=True, default="")
    anonymous = BooleanField(_("Anonymous"), default=True)
    likert_options = ArrayField(CharField(max_length=30), blank=True, default=list, verbose_name=_("Likert Options"))

    class Meta(LearningObjectMixin.Meta):
        verbose_name = _("Survey")
        verbose_name_plural = _("Surveys")

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    @property
    def is_likert(self):
        return bool(self.likert_options)


@pghistory.track()
class Submission(TimeStampedMixin):
    survey = ForeignKey(Survey, CASCADE, verbose_name=_("Survey"))
    respondent = ForeignKey(User, SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("Respondent"))
    hashed_email = CharField(_("Hashed Email"), max_length=64)
    answers = JSONField(_("Answers"))
    active = BooleanField(_("Active"), default=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Submission")
        verbose_name_plural = _("Submissions")
        indexes = [Index(fields=["hashed_email"])]
        constraints = [
            UniqueConstraint(
                fields=["survey", "respondent"],
                condition=Q(respondent__isnull=False, active=True),
                name="survey_submission_su_re_uniq",
            ),
            UniqueConstraint(
                fields=["survey", "hashed_email"], condition=Q(active=True), name="survey_submission_su_haem_uniq"
            ),
        ]

    @classmethod
    def hash_email(cls, email: str):
        return hashlib.sha256(email.lower().strip().encode()).hexdigest()
