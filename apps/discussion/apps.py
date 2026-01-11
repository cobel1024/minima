from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class DiscussionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.discussion"
    verbose_name = _("Discussion")
