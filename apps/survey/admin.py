from django.contrib import admin
from unfold.contrib.forms.widgets import WysiwygWidget

from apps.common.admin import HiddenModelAdmin, ModelAdmin, TabularInline
from apps.survey.models import Question, QuestionPaper, Submission, Survey


@admin.register(Survey)
class SurveyAdmin(ModelAdmin[Survey]):
    pass


@admin.register(QuestionPaper)
class QuestionPaperAdmin(ModelAdmin[QuestionPaper]):
    pass

    class QuestionInline(TabularInline[Question]):
        model = Question
        # orderable
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(HiddenModelAdmin[Question]):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "supplement":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin[Submission]):
    pass
