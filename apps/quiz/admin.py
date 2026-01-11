from django.contrib import admin
from unfold.contrib.forms.widgets import WysiwygWidget

from apps.common.admin import HiddenModelAdmin, ModelAdmin, TabularInline
from apps.quiz.models import Attempt, Grade, Question, QuestionPool, Quiz, Solution, Submission


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

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "supplement":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(Solution)
class SolutionAdmin(HiddenModelAdmin[Solution]):
    pass


@admin.register(Quiz)
class QuizAdmin(ModelAdmin[Quiz]):
    pass


@admin.register(Attempt)
class AttemptAdmin(ModelAdmin[Attempt]):
    class SubmissionInline(TabularInline[Submission]):
        model = Submission

    class GradeInline(TabularInline[Grade]):
        model = Grade

    inlines = (SubmissionInline, GradeInline)


@admin.register(Submission)
class SubmissionAdmin(ModelAdmin[Submission]):
    pass


@admin.register(Grade)
class GradeAdmin(ModelAdmin[Grade]):
    pass
