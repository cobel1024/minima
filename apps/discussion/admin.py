from asgiref.sync import async_to_sync
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django.utils.translation import gettext as _
from django_jsonform.forms.fields import JSONFormField
from unfold.contrib.forms.widgets import WysiwygWidget
from unfold.decorators import action

from apps.common.admin import (
    HiddenModelAdmin,
    ModelAdmin,
    ReadOnlyHiddenModelAdmin,
    ReadOnlyTabularInline,
    TabularInline,
)
from apps.common.util import AuthenticatedRequest
from apps.discussion.models import Attempt, Discussion, Grade, Post, Question, QuestionPool
from apps.operation.models import Attachment

User = get_user_model()


@admin.register(QuestionPool)
class QuestionPoolAdmin(ModelAdmin[QuestionPool]):
    class QuestionInline(TabularInline[Question]):
        model = Question

    inlines = (QuestionInline,)


@admin.register(Question)
class QuestionAdmin(HiddenModelAdmin[Question]):
    pass


@admin.register(Discussion)
class DiscussionAdmin(ModelAdmin[Discussion]):
    pass


@admin.register(Attempt)
class AttemptAdmin(ModelAdmin[Attempt]):
    class GradeInline(TabularInline[Grade]):
        model = Grade

    class PostInline(TabularInline[Post]):
        model = Post
        exclude = ("attachments",)

    inlines = (GradeInline, PostInline)


@admin.register(Post)
class PostAdmin(ModelAdmin[Post]):
    class ReplyInline(TabularInline[Post]):
        model = Post
        fk_name = "parent"
        exclude = ("attachments",)

    class AttachmentInline(TabularInline[Attachment]):
        model = Post.attachments.through
        verbose_name = _("Attachments")
        verbose_name_plural = _("Attachments")

    inlines = (ReplyInline, AttachmentInline)

    def get_fields(self, request, obj=None):
        return [f for f in super().get_fields(request, obj=obj) if f not in ("attachments",)]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "body":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)


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
        grade = Grade.objects.select_related("attempt__discussion", "attempt__question").get(pk=obj.pk)
        async_to_sync(grade.grade)(grader=request.user)

    def has_grade_permission(self, request: AuthenticatedRequest, object_id: str | int):
        return request.user.is_superuser

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "earned_details":
            return JSONFormField(
                schema={
                    "type": "dict",
                    "keys": {
                        "post": {"type": "integer", "title": _("Post")},
                        "reply": {"type": "integer", "title": _("Reply")},
                        "tutor_assessment": {"type": "integer", "title": _("Tutor Assessment")},
                    },
                },
                label=_("Earned Details"),
            )
        if db_field.name == "feedback":
            return JSONFormField(
                schema={
                    "type": "dict",
                    "keys": {
                        "tutor_assessment": {"type": "string", "title": _("Tutor Assessment"), "widget": "textarea"}
                    },
                },
                label=_("Feedback"),
                required=False,
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)
