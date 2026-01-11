from django.contrib import admin
from django.db import models
from django.db.models.expressions import Exists, OuterRef
from django.forms.models import ModelForm
from django.http import HttpRequest
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from django_jsonform.forms.fields import JSONFormField
from treebeard.forms import movenodeform_factory
from unfold.contrib.forms.widgets import WysiwygWidget

from apps.common.admin import HiddenModelAdmin, ImportExportModelAdmin, ModelAdmin, TabularInline
from apps.operation.import_export import CategoryResource
from apps.operation.models import (
    FAQ,
    Announcement,
    AnnouncementRead,
    Appeal,
    Attachment,
    Category,
    Comment,
    FAQItem,
    HonorCode,
    Inquiry,
    InquiryResponse,
    Instructor,
    Message,
    Policy,
    PolicyAgreement,
    PolicyVersion,
    Tag,
    Thread,
)


@admin.register(Announcement)
class AnnouncementAdmin(ModelAdmin[Announcement]):
    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}


@admin.register(AnnouncementRead)
class AnnouncementReadAdmin(HiddenModelAdmin[AnnouncementRead]):
    pass


@admin.register(Category)
class CategoryAdmin(ImportExportModelAdmin[Category]):
    form = movenodeform_factory(Category)
    resource_class = CategoryResource

    def get_list_display(self, request: HttpRequest):
        return ("id", "__str__")

    def get_export_queryset(self, request):
        # limit to 1000
        return super().get_export_queryset(request)[:1000]


@admin.register(Tag)
class TagAdmin(ModelAdmin[Tag]):
    pass


@admin.register(HonorCode)
class HonorCodeAdmin(ModelAdmin[HonorCode]):
    formfield_overrides = {models.TextField: {"widget": WysiwygWidget}}


@admin.register(FAQ)
class FAQAdmin(ModelAdmin[FAQ]):
    class FAQItemInline(TabularInline[FAQItem]):
        model = FAQItem
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    inlines = (FAQItemInline,)


@admin.register(FAQItem)
class FAQItemAdmin(HiddenModelAdmin[FAQItem]):
    pass


@admin.register(Instructor)
class InstructorAdmin(ModelAdmin[Instructor]):
    pass


@admin.register(Inquiry)
class InquiryAdmin(ModelAdmin[Inquiry]):
    class AttachmentInline(TabularInline[Attachment]):
        model = Inquiry.attachments.through
        verbose_name = _("Attachments")
        verbose_name_plural = _("Attachments")

    class ResponseInline(TabularInline[InquiryResponse]):
        model = InquiryResponse

    inlines = (AttachmentInline, ResponseInline)

    def get_fields(self, request, obj=None):
        return [f for f in super().get_fields(request, obj=obj) if f not in ("attachments",)]

    def get_list_display(self, request):
        return super().get_list_display(request) + ("solved",)

    @admin.display(boolean=True, description=_("Solved"))
    def solved(self, obj: Inquiry):
        return obj.solved > 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(solved=Exists(InquiryResponse.objects.filter(inquiry=OuterRef("pk"), solved__isnull=False)))

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "question":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(InquiryResponse)
class InquiryResponseAdmin(HiddenModelAdmin[InquiryResponse]):
    pass


@admin.register(Appeal)
class AppealAdmin(ModelAdmin[Appeal]):
    class AttachmentInline(TabularInline[Attachment]):
        model = Appeal.attachments.through
        verbose_name = _("Attachments")
        verbose_name_plural = _("Attachments")

    inlines = (AttachmentInline,)

    def get_fields(self, request, obj=None):
        return [f for f in super().get_fields(request, obj=obj) if f not in ("attachments",)]

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "explanation":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description=_("Explanation"))
    def display_explanation(self, obj: Appeal):
        return mark_safe(obj.cleaned_explanation)

    readonly_fields = ("display_explanation",)
    exclude = ("explanation",)


@admin.register(Attachment)
class AttachmentAdmin(ModelAdmin[Attachment]):
    pass


@admin.register(Message)
class MessageAdmin(ModelAdmin[Message]):
    pass


@admin.register(Policy)
class PolicyAdmin(ModelAdmin[Policy]):
    class PolicyVersionInline(TabularInline[PolicyVersion]):
        model = PolicyVersion

    inlines = (PolicyVersionInline,)


@admin.register(PolicyVersion)
class PolicyVersionAdmin(HiddenModelAdmin[PolicyVersion]):
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "body":
            kwargs["widget"] = WysiwygWidget
        if db_field.name == "data_category":
            return JSONFormField(
                schema={
                    "type": "dict",
                    "keys": {},
                    "additionalProperties": {"type": "array", "items": {"type": "string"}},
                }
            )

        return super().formfield_for_dbfield(db_field, request, **kwargs)


@admin.register(PolicyAgreement)
class AgreementAdmin(ModelAdmin[PolicyAgreement]):
    pass


@admin.register(Thread)
class ThreadAdmin(ModelAdmin[Thread]):
    pass


@admin.register(Comment)
class CommentAdmin(ModelAdmin[Comment]):
    class ChildCommentInline(TabularInline[Comment]):
        class ChildCommentForm(ModelForm):
            class Meta:
                model = Comment
                fields = "__all__"

            def __init__(self, *args, thread=None, user=None, **kwargs):
                if thread and not kwargs.get("instance"):
                    kwargs.setdefault("initial", {}).update({"thread": thread, "writer": user})
                super().__init__(*args, **kwargs)

        model = Comment
        fk_name = "parent"
        form = ChildCommentForm

    inlines = (ChildCommentInline,)

    def get_formset_kwargs(self, request: HttpRequest, obj: Comment | None, inline, prefix: str):
        kwargs = super().get_formset_kwargs(request, obj, inline, prefix)
        if obj and isinstance(inline, self.ChildCommentInline):
            kwargs["form_kwargs"] = {"thread": obj.thread, "user": request.user}
        return kwargs

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in "comment":
            kwargs["widget"] = WysiwygWidget
        return super().formfield_for_dbfield(db_field, request, **kwargs)
