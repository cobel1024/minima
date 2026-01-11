import logging
from typing import TYPE_CHECKING, cast

from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    AutoField,
    FileField,
    ForeignKey,
    ImageField,
    JSONField,
    ManyToManyField,
    Model,
    OneToOneField,
    QuerySet,
    TextField,
    URLField,
)
from django.forms import Select
from django.http import HttpRequest
from django.http.response import HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from import_export.admin import ImportExportModelAdmin as BaseImportExportModelAdmin
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.admin import TabularInline as UnfoldTabularInline
from unfold.contrib.forms.widgets import ArrayWidget
from unfold.contrib.import_export.forms import ExportForm, ImportForm
from unfold.forms import UserChangeForm, UserCreationForm
from unfold.sites import UnfoldAdminSite
from unfold.widgets import UnfoldAdminSelectWidget, UnfoldAdminTextareaWidget

from apps.common.util import ArrayField as FixedArrayField


class BaseModelAdmin(UnfoldModelAdmin):
    formfield_overrides = {
        ArrayField: {"form_class": FixedArrayField, "widget": ArrayWidget},
        TextField: {"widget": UnfoldAdminTextareaWidget(attrs={"rows": 5})},
        JSONField: {"widget": UnfoldAdminTextareaWidget(attrs={"rows": 5})},
    }

    def get_form(self, request: HttpRequest, obj: Model | None = None, change: bool = False, **kwargs: object):
        form = super().get_form(request, obj, change=change, **kwargs)
        if base_fields := getattr(form, "base_fields", {}):
            for field in base_fields.values():
                if isinstance(field.widget, Select) and not hasattr(field.widget, "__unfold_styled__"):
                    new_widget = UnfoldAdminSelectWidget(attrs=field.widget.attrs)
                    new_widget.choices = field.widget.choices
                    if hasattr(field.widget, "is_required"):
                        new_widget.is_required = field.widget.is_required
                    field.widget = new_widget
                    setattr(field.widget, "__unfold_styled__", True)
        return form


class BaseTabularInline(UnfoldTabularInline):
    pass


if TYPE_CHECKING:
    # unfold is not ready to be used in type checker
    from django.contrib.admin import ModelAdmin as BaseModelAdmin
    from django.contrib.admin import TabularInline as BaseTabularInline


log = logging.getLogger(__name__)

User = get_user_model()

COMMON_SEARCH_FIELDS = [
    "id",
    "name",
    "title",
    "description",
    "body",
    "text",
    "summary",
    "email",
    "phone",
    "contact",
    "code",
    "slug",
    "number",
    "reference",
    "status",
    "category",
    "type",
    "format",
]


class GenericEditLinkMixin:
    if TYPE_CHECKING:
        readonly_fields: tuple[str, ...]
        model: type[Model]

    def add_generic_edit_links(self):
        generic_fk: GenericForeignKey | None = None
        for field in self.model._meta.get_fields():
            if isinstance(field, GenericForeignKey):
                generic_fk = field
                break

        if generic_fk:
            edit_method_name = f"{generic_fk.name}_edit_link"
            if not hasattr(self, edit_method_name) and edit_method_name not in self.readonly_fields:
                self.readonly_fields = tuple(self.readonly_fields) + (edit_method_name,)

                def make_edit_link_method(gfk_field: GenericForeignKey):
                    @admin.display(description=f"{_(gfk_field.name.capitalize())} {_('Edit')}")
                    def edit_link_method(self: object, obj: Model):
                        object_type = getattr(obj, gfk_field.ct_field, None)
                        object_id = getattr(obj, gfk_field.fk_field, None)

                        if not object_type or not object_id:
                            return "-"

                        return format_html(
                            '<a href="{}" target="_blank" class="button"><div style="text-align: center;">{}</div></a>',
                            reverse(f"admin:{object_type.app_label}_{object_type.model}_change", args=[object_id]),
                            _("Edit"),
                        )

                    return edit_link_method

                setattr(self, edit_method_name, make_edit_link_method(generic_fk).__get__(self, self.__class__))


class ModelAdmin[T: Model](GenericEditLinkMixin, BaseModelAdmin):
    list_per_page = 20

    def __init__(self, model: type[T], admin_site: AdminSite):
        super().__init__(model, admin_site)
        self.add_generic_edit_links()
        if not hasattr(self, "list_display"):
            self.list_display = ()

        self._computed_autocomplete_fields: list[str] = []
        self._computed_search_fields: list[str] = []
        self._computed_list_display: list[str] = []
        self._computed_readonly_fields: list[str] = []

        for field in model._meta.fields:
            if isinstance(field, ForeignKey):
                if field.name not in self.autocomplete_fields:
                    self._computed_autocomplete_fields.append(field.name)

                for related_field in cast(T, field.related_model)._meta.fields:
                    if related_field.name in COMMON_SEARCH_FIELDS and not isinstance(related_field, ForeignKey):
                        self._computed_search_fields.append(f"{field.name}__{related_field.name}")

            elif field.name in COMMON_SEARCH_FIELDS:
                self._computed_search_fields.append(field.name)

            if field.name not in ["password", "created", "token"] and type(field) not in (
                ArrayField,
                OneToOneField,
                ForeignKey,
                AutoField,
                TextField,
                JSONField,
                URLField,
                ImageField,
                FileField,
            ):
                self._computed_list_display.append(field.name)

            if field.name in ["created", "modified", "context"]:
                self._computed_readonly_fields.append(field.name)

        for field in model._meta.many_to_many:
            if field.name not in self.autocomplete_fields:
                self._computed_autocomplete_fields.append(field.name)

    def get_autocomplete_fields(self, request):
        return tuple(list(super().get_autocomplete_fields(request)) + self._computed_autocomplete_fields)

    def get_search_fields(self, request):
        return tuple(list(super().get_search_fields(request)) + self._computed_search_fields)

    def get_list_display(self, request: HttpRequest):
        base = [f for f in self.list_display if f not in ["__str__"]]
        return tuple(cast(str, f) for f in base + self._computed_list_display)

    def get_readonly_fields(self, request, obj=None):
        return tuple(list(super().get_readonly_fields(request, obj)) + self._computed_readonly_fields)

    def get_queryset(self, request: HttpRequest) -> QuerySet[T]:
        qs = super().get_queryset(request)

        select_related_fields: list[str] = []
        for field in self.model._meta.fields:
            if isinstance(field, ForeignKey):
                select_related_fields.append(field.name)

        if select_related_fields:
            qs = qs.select_related(*select_related_fields)

        prefetch_related_fields: list[str] = []
        for field in self.model._meta.many_to_many:
            prefetch_related_fields.append(field.name)

        if prefetch_related_fields:
            qs = qs.prefetch_related(*prefetch_related_fields)

        if "created" in [f.name for f in self.model._meta.fields]:
            qs = qs.order_by("-created")

        return qs

    def response_change(self, request, obj):
        prefix = f"{obj._meta.app_label}_{obj._meta.model_name}_"
        for key in request.POST:
            if key.startswith(prefix):
                action_name = key.replace(prefix, "")
                if action_name in self._extract_action_names(self.actions_submit_line):  # type: ignore :used in extra actions
                    return HttpResponseRedirect(request.path)
        return super().response_change(request, obj)


class ImportExportModelAdmin[T: Model](ModelAdmin[T], BaseImportExportModelAdmin):
    import_form_class = ImportForm
    export_form_class = ExportForm


class TabularInline[T: Model](GenericEditLinkMixin, BaseTabularInline):
    hide_title = True
    formfield_overrides = {
        ArrayField: {"form_class": FixedArrayField, "widget": ArrayWidget},
        TextField: {"widget": UnfoldAdminTextareaWidget(attrs={"rows": 2})},
        JSONField: {"widget": UnfoldAdminTextareaWidget(attrs={"rows": 2})},
    }
    extra = 0
    ordering = ("id",)
    per_page = 10

    if TYPE_CHECKING:
        readonly_fields: tuple[str, ...]

    def __init__(self, parent_model: type[T], admin_site: AdminSite):
        super().__init__(parent_model, admin_site)

        # generic relation edit link
        self.add_generic_edit_links()

        if self._is_foreign_key_inline(parent_model):
            self.add_nested_inline_links()

    def get_autocomplete_fields(self, request):
        fields = list(super().get_autocomplete_fields(request))
        for field in self.model._meta.fields:
            if isinstance(field, ForeignKey) and field.name not in fields:
                fields.append(field.name)

        for field in self.model._meta.many_to_many:
            if field.name not in fields:
                fields.append(field.name)
        return fields

    def _is_foreign_key_inline(self, parent_model: type[T]) -> bool:
        for field in parent_model._meta.get_fields():
            if isinstance(field, ManyToManyField):
                if hasattr(field.remote_field, "through"):
                    through_model = field.remote_field.through
                    if through_model == self.model:
                        return False
        return True

    def get_readonly_fields(self, request: HttpRequest, obj: T | None = None):
        readonly_fields = list(super().get_readonly_fields(request, obj))
        timestamp_fields = []
        for field_name in ["created", "modified"]:
            if any(f.name == field_name for f in self.model._meta.fields):
                timestamp_fields.append(field_name)

        return timestamp_fields + readonly_fields

    def add_nested_inline_links(self):
        link_method_name = f"{self.model._meta.model_name}_detail_link"

        if not hasattr(self, link_method_name) and link_method_name not in self.readonly_fields:
            self.readonly_fields = tuple(self.readonly_fields) + (link_method_name,)

            def make_detail_link_method(model_class: type[Model]):
                @admin.display(description=f"{_('Detail')}")
                def detail_link_method(self: object, obj: Model):
                    if obj.pk:
                        change_url = reverse(
                            f"admin:{model_class._meta.app_label}_{model_class._meta.model_name}_change", args=[obj.pk]
                        )
                        return format_html(
                            '<a href="{}" target="_blank" class="button"><div style="text-align: center;">{}</div></a>',
                            change_url,
                            _("Open"),
                        )
                    return "-"

                return detail_link_method

            setattr(self, link_method_name, make_detail_link_method(self.model).__get__(self, self.__class__))


class HiddenModelAdmin[T: Model](ModelAdmin[T]):
    def has_module_permission(self, request: HttpRequest):
        return False


class ReadOnlyModelAdmin[T: Model](ModelAdmin[T]):
    def has_add_permission(self, request: HttpRequest, obj: Model | None = None):
        return False

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None):
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None):
        return False


class ReadOnlyHiddenModelAdmin[T: Model](ReadOnlyModelAdmin[T], HiddenModelAdmin[T]):
    pass


class ReadOnlyTabularInline[T: Model](TabularInline[T]):
    def has_add_permission(self, request: HttpRequest, obj: object | None = None):
        return False

    def has_change_permission(self, request: HttpRequest, obj: object | None = None):
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None):
        return False


class BaseUserAdmin(ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    list_filter_submit = True


# register django models for autocomplete

admin.site.unregister(Group)


@admin.register(ContentType)
class ContentTypeAdmin(HiddenModelAdmin[ContentType]):
    pass


@admin.register(Permission)
class PermissionAdmin(HiddenModelAdmin[Permission]):
    pass


@admin.register(Group)
class GroupAdmin(HiddenModelAdmin[Group]):
    pass


# reorder admin app list


class CustomAdminSite(UnfoldAdminSite):
    def get_app_list(self, request, app_label=None):
        app_dict = self._build_app_dict(request, app_label)
        app_list = list(app_dict.values())
        return app_list


admin.site.__class__ = CustomAdminSite
