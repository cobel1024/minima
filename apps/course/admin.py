from asgiref.sync import async_to_sync
from django.contrib import admin
from django.utils.translation import gettext as _
from django_jsonform.forms.fields import JSONFormField
from unfold.decorators import action

from apps.common.admin import HiddenModelAdmin, ModelAdmin, TabularInline
from apps.common.util import AuthenticatedRequest
from apps.competency.models import Certificate
from apps.course.models import (
    TEMPLATE_SCHEDULES,
    Assessment,
    Course,
    CourseInstructor,
    CourseSurvey,
    Engagement,
    Gradebook,
    GradingPolicy,
    Lesson,
    LessonMedia,
    MessagePreset,
)
from apps.operation.models import Category


@admin.register(Course)
class CourseAdmin(ModelAdmin[Course]):
    class CategoryInline(TabularInline[Category]):
        model = Course.categories.through
        verbose_name = _("Category")
        verbose_name_plural = _("Categories")

    class CertificateInline(TabularInline[Certificate]):
        model = Course.certificates.through
        verbose_name = _("Certificate")
        verbose_name_plural = _("Certificates")

    class CourseInstructorInline(TabularInline[CourseInstructor]):
        model = CourseInstructor
        # orderable
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    class CourseSurveyInline(TabularInline[CourseSurvey]):
        model = CourseSurvey

    class AssessmentInline(TabularInline[Assessment]):
        model = Assessment

    class LessonInline(TabularInline[Lesson]):
        model = Lesson
        # orderable
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    class GradingPolicyInline(TabularInline[GradingPolicy]):
        model = GradingPolicy

    class RelatedCourseInline(TabularInline[Course]):
        model = Course.related_courses.through
        fk_name = "from_course"
        verbose_name = _("Related Course")
        verbose_name_plural = _("Related Courses")

    inlines = (
        CategoryInline,
        CertificateInline,
        CourseInstructorInline,
        CourseSurveyInline,
        LessonInline,
        AssessmentInline,
        GradingPolicyInline,
        RelatedCourseInline,
    )

    def get_fields(self, request, obj=None):
        return [
            f
            for f in super().get_fields(request, obj=obj)
            if f not in ("categories", "certificates", "related_courses")
        ]


@admin.register(Lesson)
class LessonAdmin(HiddenModelAdmin[Lesson]):
    class LessonMediaInline(TabularInline[LessonMedia]):
        model = LessonMedia
        # orderable
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    inlines = (LessonMediaInline,)


@admin.register(GradingPolicy)
class GradingPolicyAdmin(HiddenModelAdmin[GradingPolicy]):
    pass


@admin.register(CourseInstructor)
class CourseInstructorAdmin(HiddenModelAdmin[CourseInstructor]):
    pass


@admin.register(CourseSurvey)
class CourseSurveyAdmin(HiddenModelAdmin[CourseSurvey]):
    pass


@admin.register(Assessment)
class AssessmentAdmin(HiddenModelAdmin[Assessment]):
    pass


@admin.register(LessonMedia)
class LessonMediaAdmin(HiddenModelAdmin[LessonMedia]):
    pass


@admin.register(Engagement)
class EngagementAdmin(ModelAdmin[Engagement]):
    class GradebookInline(TabularInline[Gradebook]):
        model = Gradebook

    inlines = (GradebookInline,)

    actions_submit_line = ["grade"]

    @action(description=_("Grade"), permissions=["grade"])
    def grade(self, request: AuthenticatedRequest, obj: Engagement):
        async_to_sync(Engagement.grade)(course_id=obj.course.id, learner_id=obj.learner.pk, grader=request.user)

    def has_grade_permission(self, request: AuthenticatedRequest, object_id: str | int):
        return request.user.is_superuser


@admin.register(Gradebook)
class GradebookAdmin(ModelAdmin[Gradebook]):
    pass


@admin.register(MessagePreset)
class MessagePresetAdmin(HiddenModelAdmin[MessagePreset]):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "templates":
            return JSONFormField(
                schema={"type": "array", "items": {"type": "string", "choices": list(TEMPLATE_SCHEDULES.keys())}}
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)
