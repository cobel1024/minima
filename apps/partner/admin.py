from django.contrib import admin
from django.http.request import HttpRequest
from django.utils.translation import gettext_lazy as _
from unfold.contrib.filters.admin.dropdown_filters import RelatedDropdownFilter
from unfold.contrib.filters.admin.text_filters import FieldTextFilter

from apps.common.admin import (
    HiddenModelAdmin,
    ImportExportModelAdmin,
    ModelAdmin,
    ReadOnlyHiddenModelAdmin,
    TabularInline,
)
from apps.partner.import_export import EmployeeResource
from apps.partner.models import BusinessSite, Cohort, CohortEmployee, CohortStaff, Employee, Partner


@admin.register(Partner)
class PartnerAdmin(ModelAdmin[Partner]):
    class BusinessSiteInline(TabularInline[BusinessSite]):
        model = BusinessSite

        @admin.display(description="ID")
        def id_(self, obj: Partner):
            return obj.pk

        def get_readonly_fields(self, request: HttpRequest, obj: BusinessSite | None = None):
            readonly_fields = list(super().get_readonly_fields(request, obj))
            return ["id_"] + readonly_fields

    inlines = (BusinessSiteInline,)


@admin.register(BusinessSite)
class BusinessSiteAdmin(HiddenModelAdmin[BusinessSite]):
    pass


@admin.register(Employee)
class EmployeeAdmin(ImportExportModelAdmin[Employee]):
    class CohortEmployeeInline(TabularInline[CohortEmployee]):
        model = CohortEmployee

    class EmployeeEventInline(TabularInline[Employee.pgh_event_model]):
        model = Employee.pgh_event_model

    inlines = (CohortEmployeeInline, EmployeeEventInline)

    resource_class = EmployeeResource

    list_filter_submit = True
    list_filter = [
        ("site__partner", RelatedDropdownFilter),
        ("site", RelatedDropdownFilter),
        ("team", FieldTextFilter),
        ("cohortemployee__cohort", RelatedDropdownFilter),
    ]

    @admin.display(description=_("User"), boolean=True)
    def linked_user(self, obj: Employee):
        return bool(obj.user)

    def get_export_queryset(self, request):
        # limit to 1000
        return super().get_export_queryset(request)[:1000]

    def get_list_display(self, request: HttpRequest):
        list_display = super().get_list_display(request)
        return tuple(f for f in list_display if f not in ["encrypted_id_number"]) + ("linked_user",)


@admin.register(Cohort)
class CohortAdmin(ModelAdmin[Cohort]):
    class StaffInline(TabularInline[CohortStaff]):
        model = CohortStaff

    class EmployeeInline(TabularInline[CohortEmployee]):
        model = CohortEmployee
        exclude = ("encrypted_id_number", "employment_status", "employment_type")

    exclude = ("employees",)
    inlines = (StaffInline, EmployeeInline)


@admin.register(CohortStaff)
class CohortStaffAdmin(HiddenModelAdmin[CohortStaff]):
    pass


@admin.register(CohortEmployee)
class CohortEmployeeAdmin(HiddenModelAdmin[CohortEmployee]):
    pass


@admin.register(Employee.pgh_event_model)
class CohortEmployeeEventAdmin(ReadOnlyHiddenModelAdmin[Employee.pgh_event_model]):
    pass
