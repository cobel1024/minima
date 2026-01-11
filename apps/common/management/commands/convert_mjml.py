import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template import Context
from django.template import Template as DjangoTemplate
from django.utils.translation import gettext as _
from mjml import mjml2html


class Command(BaseCommand):
    help = _("Convert MJML templates to HTML for all apps")

    def handle(self, *args: object, **options: dict[str, object]):
        base_dir = Path(settings.BASE_DIR)
        apps_dir = base_dir / "apps"
        common_partial_dir = apps_dir / "common" / "mjml" / "partial"

        if not apps_dir.exists():
            self.stdout.write(self.style.ERROR(_("Apps directory not found")))
            return

        converted_count = 0
        for app_dir in apps_dir.iterdir():
            if not app_dir.is_dir() or app_dir.name.startswith("_"):
                continue

            mjml_dir = app_dir / "mjml"
            if not mjml_dir.exists():
                continue

            if self.convert_app_mjml(mjml_dir, app_dir.name, common_partial_dir):
                converted_count += 1

        if converted_count == 0:
            self.stdout.write(self.style.WARNING(_("\nNo MJML files found in any app")))
        else:
            self.stdout.write(self.style.SUCCESS(_(f"\n✓ Converted MJML files in {converted_count} app(s)")))

    def convert_app_mjml(self, mjml_dir: Path, app_name: str, common_partial_dir: Path) -> bool:
        mjml_files = list(mjml_dir.glob("*.mjml"))
        if not mjml_files:
            return False

        mail_dir = mjml_dir.parent / "templates" / app_name / "mail"
        mail_dir.mkdir(parents=True, exist_ok=True)

        static_context = Context({
            "platform_name": settings.PLATFORM_NAME,
            "platform_address": settings.PLATFORM_ADDRESS,
            "privacy_policy_url": settings.PRIVACY_POLICY_URL,
            "terms_url": settings.TERMS_URL,
            "support_email": settings.DEFAULT_FROM_EMAIL,
        })

        for mjml_file in mjml_files:
            html_file = mail_dir / f"{mjml_file.stem}.html"

            with open(mjml_file, "r", encoding="utf-8") as file:
                mjml_str = file.read()

            root_start = mjml_str.find("<mjml>")
            root_end = mjml_str.find("</mjml>") + len("</mjml>")

            if root_start == -1 or root_end == -1:
                self.stdout.write(self.style.ERROR(_(f"  ✗ Invalid MJML file: {mjml_file.name}")))
                continue

            before_root = mjml_str[:root_start]
            after_root = mjml_str[root_end:]

            def partial_loader(path: str):
                app_partial = mjml_dir / path
                if app_partial.exists():
                    with open(app_partial, "r", encoding="utf-8") as file:
                        return file.read()

                common_partial = common_partial_dir / Path(path).name
                if common_partial.exists():
                    with open(common_partial, "r", encoding="utf-8") as file:
                        return file.read()

                raise FileNotFoundError(f"Partial not found: {path}")

            body = mjml_str[root_start:root_end]
            html_content = before_root + mjml2html(body, include_loader=partial_loader) + after_root

            html_content = DjangoTemplate(html_content).render(static_context)
            html_content = self.restore_dynamic_placeholder(html_content)

            with open(html_file, "w", encoding="utf-8") as file:
                file.write(html_content)

            self.stdout.write(self.style.SUCCESS(_(f"  ✓ {mjml_file.stem}.html")))

        return True

    @staticmethod
    def restore_dynamic_placeholder(template_str: str):
        return re.sub(r"\{\s*(\w+)\s*\}", r"{{ \1 }}", template_str)
