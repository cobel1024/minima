import logging
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _

from apps.partner.models import Partner

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = _("Create platform partner")

    def handle(self, *args: object, **options: dict[str, object]):
        logo_path = Path(settings.BASE_DIR) / "static/image/logo/logo.png"
        with logo_path.open("rb") as f:
            logo = ContentFile(f.read(), name="logo.png")

        partner, created = Partner.objects.get_or_create(
            name=settings.PLATFORM_NAME,
            defaults={
                "description": _("%s is a platform for education.") % settings.PLATFORM_NAME,
                "phone": settings.PLATFORM_PHONE_NUMBER,
                "email": settings.DEFAULT_FROM_EMAIL,
                "address": settings.PLATFORM_ADDRESS,
                "logo": logo,
                "website": settings.PLATFORM_BASE_URL,
            },
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"Partner {partner} created"))
        else:
            self.stdout.write(self.style.WARNING(f"Partner {partner} already exists"))
