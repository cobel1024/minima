import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.template import Context
from django.template import Template as DjangoTemplate
from django.utils.translation import gettext as _
from mjml import mjml2html


class Command(BaseCommand):
    help = _("Convert MJML templates to HTML")

    def handle(self, *args: object, **options: dict[str, object]):
        app_root = Path(__file__).resolve().parent.parent.parent
        mjml_dir = app_root / "mjml"
        mail_dir = app_root / "templates" / "course" / "mail"

        mail_dir.mkdir(parents=True, exist_ok=True)
        mjml_files = list(mjml_dir.glob("*.mjml"))

        if not mjml_files:
            self.stdout.write(self.style.WARNING(_("No MJML files found")))
            return

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
                self.stdout.write(self.style.ERROR(_("Invalid MJML file: %(name)s") % {"name": mjml_file.name}))
                continue

            before_root = mjml_str[:root_start]
            after_root = mjml_str[root_end:]

            def partial_loader(path: str):
                with open(mjml_dir / path, "r", encoding="utf-8") as file:
                    partial = file.read()
                return partial

            body = mjml_str[root_start:root_end]
            html_content = before_root + mjml2html(body, include_loader=partial_loader) + after_root

            html_content = DjangoTemplate(html_content).render(static_context)
            html_content = self.restore_dynamic_placeholder(html_content)

            with open(html_file, "w", encoding="utf-8") as file:
                file.write(html_content)

            self.stdout.write(self.style.SUCCESS(_("Successfully converted %(name)s") % {"name": mjml_file.stem}))

    @staticmethod
    def restore_dynamic_placeholder(template_str: str):
        return re.sub(r"\{\s*(\w+)\s*\}", r"{{ \1 }}", template_str)
