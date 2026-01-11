from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PartnerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.partner"
    verbose_name = _("Partner")
