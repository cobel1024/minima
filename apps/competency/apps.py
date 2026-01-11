from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CompetencyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.competency"
    verbose_name = _("Competency")
