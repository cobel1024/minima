from asgiref.sync import async_to_sync
from django.contrib import admin
from django.http import HttpRequest
from django.utils.translation import gettext as _
from django_jsonform.forms.fields import JSONFormField
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import action

from apps.assignment.models import (
    Assignment,
    Attempt,
    Grade,
    PerformanceLevel,
    PlagiarismCheck,
    Question,
    QuestionPool,
    Rubric,
    RubricCriterion,
    Solution,
    Submission,
)
from apps.common.admin import (
    HiddenModelAdmin,
    ModelAdmin,
    ReadOnlyHiddenModelAdmin,
    ReadOnlyTabularInline,
    TabularInline,
)
from apps.common.util import AuthenticatedRequest
from apps.operation.models import Attachment


@admin.register(QuestionPool)
class QuestionPoolAdmin(ModelAdmin[QuestionPool]):
    class QuestionInline(TabularInline[Question]):
        model = Question

    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(HiddenModelAdmin[Question]):
    class SolutionInline(TabularInline[Solution]):
        model = Solution

    inlines = (SolutionInline,)

    def formfield_for_dbfield(self, db_field, request, **kwargs: object):
        if db_field.name == "supplement":
            kwargs["widget"] = WysiwygWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Solution)
class SolutionAdmin(HiddenModelAdmin[Solution]):
    pass


@admin.register(Rubric)
class RubricAdmin(ModelAdmin[Rubric]):
    class RubricCriterionInline(TabularInline[RubricCriterion]):
        model = RubricCriterion
        # ordering = ("name")

    inlines = (RubricCriterionInline,)


@admin.register(RubricCriterion)
class RubricCriterionAdmin(HiddenModelAdmin[RubricCriterion]):
    class PerformanceLevelInline(TabularInline[PerformanceLevel]):
        model = PerformanceLevel
        # ordering = ("point", "name")

    inlines = (PerformanceLevelInline,)


@admin.register(PerformanceLevel)
class PerformanceLevelAdmin(HiddenModelAdmin[PerformanceLevel]):
    pass


@admin.register(Assignment)
class AssignmentAdmin(ModelAdmin[Assignment]):
    pass


@admin.register(Attempt)
class AttemptAdmin(ModelAdmin[Attempt]):
    class SubmissionInline(TabularInline[Submission]):
        model = Submission
        exclude = ("extracted_text",)

    class GradeInline(TabularInline[Grade]):
        model = Grade

    class PlagiarismCheckInline(TabularInline[PlagiarismCheck]):
        model = PlagiarismCheck

    inlines = (SubmissionInline, GradeInline, PlagiarismCheckInline)


@admin.register(Submission.pgh_event_model)
class SubmissionEventAdmin(ReadOnlyHiddenModelAdmin[Submission.pgh_event_model]):
    pass


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin[Submission]):
    class AttachmentInline(TabularInline[Attachment]):
        model = Submission.attachments.through
        verbose_name = _("Attachments")
        verbose_name_plural = _("Attachments")

    class SubmissionEventInline(ReadOnlyTabularInline[Submission.pgh_event_model]):
        model = Submission.pgh_event_model
        verbose_name = _("Submission History")
        verbose_name_plural = _("Submission Histories")
        exclude = ("extracted_text", "answer")

    inlines = (AttachmentInline, SubmissionEventInline)

    def formfield_for_dbfield(self, db_field, request, **kwargs: object):
        if db_field.name == "answer":
            kwargs["widget"] = WysiwygWidget()
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def get_fields(self, request, obj=None):
        return [f for f in super().get_fields(request, obj=obj) if f not in ("attachments",)]


@admin.register(Grade.pgh_event_model)
class GradeEventAdmin(ReadOnlyHiddenModelAdmin[Grade.pgh_event_model]):
    pass


@admin.register(Grade)
class GradeAdmin(ModelAdmin[Grade]):
    class GradeEventInline(ReadOnlyTabularInline[Grade.pgh_event_model]):
        model = Grade.pgh_event_model
        verbose_name = _("Grading History")
        verbose_name_plural = _("Grading Histories")

    inlines = (GradeEventInline,)

    actions_submit_line = ["grade"]

    @action(description=_("Grade"), permissions=["grade"])
    def grade(self, request: HttpRequest, obj: Grade):
        grade = Grade.objects.select_related("attempt__assignment", "attempt__question__solution__rubric").get(
            pk=obj.pk
        )
        async_to_sync(grade.grade)(grader=request.user)

    def has_grade_permission(self, request: AuthenticatedRequest, object_id: str | int):
        return request.user.is_staff

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "earned_details":
            return JSONFormField(
                schema={"type": "dict", "keys": {}, "additionalProperties": {"type": "integer"}},
                label=_("Earned Details"),
            )
        if db_field.name == "feedback":
            return JSONFormField(
                schema={"type": "dict", "keys": {}, "additionalProperties": {"type": "string", "widget": "textarea"}},
                label=_("Feedback"),
                required=False,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(PlagiarismCheck)
class PlagiarismCheckAdmin(ModelAdmin[PlagiarismCheck]):
    pass
