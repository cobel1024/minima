import copy
import json
from typing import Any

import unfold.fields
import unfold.utils
from django.apps import AppConfig
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from unfold.sites import UnfoldAdminSite


class CommonConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.common"
    verbose_name = _("Apps")

    def ready(self):
        # patch: prettify json
        def prettify_json(data: Any, encoder: Any) -> str | None:
            response = json.dumps(data, sort_keys=True, indent=4, cls=encoder, ensure_ascii=False)
            return mark_safe(f'<div class="prettify-json">{response}</div>')

        setattr(unfold.utils, "prettify_json", prettify_json)
        setattr(unfold.fields, "prettify_json", prettify_json)

        # patch: unfold side bar default options
        def patched_get_sidebar_list(self, request):
            navigation = self._get_value(self._get_config("SIDEBAR", request).get("navigation"), request)

            if not navigation:
                app_list = self.get_app_list(request)
                navigation = []

                for app in app_list:
                    items = []
                    for model in app["models"]:
                        items.append({"title": model["name"], "link": model["admin_url"]})

                    if items:
                        navigation.append({"title": app["name"], "collapsible": True, "items": items})

            tabs = self._get_value(self._get_config("TABS", request), request) or []
            results = []

            for group in copy.deepcopy(navigation):
                group["items"] = self._get_navigation_items(request, group["items"], tabs)
                results.append(group)

            return results

        setattr(UnfoldAdminSite, "get_sidebar_list", patched_get_sidebar_list)
