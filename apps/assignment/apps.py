from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AssignmentConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.assignment"
    verbose_name = _("Assignment")
