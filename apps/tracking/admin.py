from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from pghistory.models import Context as HistoryContext

from apps.common.admin import HiddenModelAdmin, ReadOnlyModelAdmin
from apps.tracking.models import HotEvent, SyncRecord


@admin.register(HistoryContext)
class ContextAdmin(HiddenModelAdmin[HistoryContext]):
    # fix: context autocomplete
    pass


@admin.register(HotEvent)
class HotEventsAdmin(ReadOnlyModelAdmin[HotEvent]):
    @admin.display(description=_("Diff"))
    def pgh_diff_keys(self, obj: HotEvent):
        if not obj.pgh_diff:
            return ""
        return ", ".join(obj.pgh_diff.keys())

    @admin.display(description=_("Admin"), boolean=True)
    def is_admin(self, obj: HotEvent):
        return obj.pgh_context.get("is_admin") if obj.pgh_context else None

    @admin.display(description=_("URL"))
    def url(self, obj: HotEvent):
        return obj.pgh_context.get("url", "") if obj.pgh_context else ""

    @admin.display(description=_("Model"))
    def obj_model(self, obj: HotEvent):
        return _(obj.pgh_obj_model.split(".")[-1])

    @admin.display(description=_("Kind"))
    def kind(self, obj: HotEvent):
        return _(obj.pgh_label.capitalize())

    def get_list_display(self, request):
        return ("id", "pgh_created_at", "obj_model", "pgh_obj_id", "kind", "pgh_diff_keys", "is_admin", "url")


@admin.register(SyncRecord)
class SyncRecordAdmin(ReadOnlyModelAdmin[SyncRecord]):
    pass
