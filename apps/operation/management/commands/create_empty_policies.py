import logging

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.operation.models import Policy

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _("Create empty policies")

    def handle(self, *args: object, **options: dict[str, object]):
        for i, (value, label) in enumerate(Policy.KindChoices.choices):
            policy, created = Policy.objects.get_or_create(
                kind=value,
                defaults={
                    "title": str(label),
                    "description": str(label),
                    "active": True,
                    "mandatory": value != Policy.KindChoices.MARKETING_POLICY.value,
                    "show_on_join": True,
                    "priority": i,
                },
            )

            if created:
                policy.policyversion_set.create(
                    body=_("Write your %s policy here") % label,
                    data_category={},
                    version="1.0",
                    effective_date=timezone.now(),
                )
                self.stdout.write(self.style.SUCCESS(_("Successfully created policy %s") % policy.title))
            else:
                self.stdout.write(self.style.WARNING(_("Policy %s already exists") % policy.title))
