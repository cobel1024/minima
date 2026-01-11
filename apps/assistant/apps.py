from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AssistantConfig(AppConfig):
    name = "apps.assistant"
    verbose_name = _("AI Assistant")
