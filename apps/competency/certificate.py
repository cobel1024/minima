import logging
from io import BytesIO
from typing import Literal, TypedDict

import pypdfium2 as pdfium
import qrcode
from asgiref.sync import sync_to_async
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.utils.translation import gettext as _
from fpdf import FPDF

log = logging.getLogger(__name__)


CertificateControlType = Literal[
    "document_title",
    "document_number",
    "completion_title",
    "completion_period",
    "completion_hours",
    "recipient_name",
    "recipient_birth_date",
    "issuer_name",
    "issue_date",
    "expiration_date",
    "verification_qr",
]


class CertificateControlDict(TypedDict):
    type: CertificateControlType
    x_percentage: float
    y_percentage: float
    font_size: int
    font_family: str
    font_weight: str
    font_color: str
    text_align: Literal["left", "center", "right"]
    label: str


class CertificateTemplateDataDict(TypedDict):
    page_size: tuple[int, int]
    controls: list[CertificateControlDict]


class CertificateAwardDataDict(TypedDict):
    document_title: str
    completion_title: str
    completion_period: str
    completion_hours: str
    recipient_name: str
    recipient_birth_date: str


class CertificateAwardFullDataDict(CertificateAwardDataDict):
    document_number: str
    issuer_name: str
    issue_date: str
    expiration_date: str


def hex_to_rgb(hex_color: str):
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


async def generate_thumbnail_from_pdf(pdf_bytes: bytes | bytearray) -> BytesIO:
    pdf = await sync_to_async(pdfium.PdfDocument)(pdf_bytes)
    page = pdf[0]

    bitmap = await sync_to_async(page.render)(scale=150 / 72, rotation=0)
    pil_image = await sync_to_async(bitmap.to_pil)()
    pil_image.thumbnail((400, 566))

    thumbnail_buffer = BytesIO()
    pil_image.save(thumbnail_buffer, "PNG", optimize=True)
    thumbnail_buffer.seek(0)

    await sync_to_async(pdf.close)()

    return thumbnail_buffer


async def generate_certificate(
    background_image: UploadedFile,
    template: CertificateTemplateDataDict,
    data: CertificateAwardFullDataDict,
    verification_url: str,
) -> tuple[ContentFile, ContentFile]:
    page_width, page_height = template["page_size"]

    pdf = FPDF(orientation="P", unit="mm", format=(page_width, page_height))
    pdf.add_page()

    pdf.add_font("Noto", "", fname="/usr/share/fonts/noto/NotoSansCJK-Regular.ttc")
    pdf.add_font("Noto", "B", fname="/usr/share/fonts/noto/NotoSansCJK-Bold.ttc")

    with BytesIO() as bg_buffer:
        for chunk in background_image.chunks():
            bg_buffer.write(chunk)
        bg_buffer.seek(0)
        pdf.image(bg_buffer, x=0, y=0, w=page_width, h=page_height)

    qr_image = None
    for control in template["controls"]:
        if control["type"] == "verification_qr":
            qr = qrcode.QRCode(version=1, box_size=10, border=2)
            qr.add_data(verification_url)
            qr.make(fit=True)
            qr_image = qr.make_image(fill_color="black", back_color="white")
            break

    for control in template["controls"]:
        control_type = control["type"]
        x = control["x_percentage"] * page_width / 100
        y = control["y_percentage"] * page_height / 100

        if control_type == "verification_qr" and qr_image:
            qr_size = 20
            qr_buffer = BytesIO()
            qr_image.save(qr_buffer, "PNG")
            qr_buffer.seek(0)
            pdf.image(qr_buffer, x=x, y=y, w=qr_size)

        else:
            text = data.get(control_type, "")
            if not text:
                continue

            font_size = control["font_size"]
            font_style = "B" if control["font_weight"] == "bold" else ""

            pdf.set_font("Noto", font_style, font_size)

            r, g, b = hex_to_rgb(control["font_color"])
            pdf.set_text_color(r, g, b)

            label = control.get("label", "")
            align = control["text_align"]

            if label:
                label_text = label + " : "
                label_width = pdf.get_string_width(label_text)
                full_text = label_text + str(text)
                full_width = pdf.get_string_width(full_text)

                if align == "center":
                    start_x = x - full_width / 2
                elif align == "right":
                    start_x = x - full_width
                else:
                    start_x = x

                pdf.set_xy(start_x, y)
                pdf.cell(label_width, font_size / 2, label_text, align="L")
                pdf.cell(0, font_size / 2, str(text), align="L")
            else:
                text_width = pdf.get_string_width(str(text))

                if align == "center":
                    pdf.set_xy(x - text_width / 2, y)
                elif align == "right":
                    pdf.set_xy(x - text_width, y)
                else:
                    pdf.set_xy(x, y)

                pdf.cell(0, font_size / 2, str(text), align="L")

    pdf_bytes = bytes(pdf.output())

    thumbnail_buffer = await generate_thumbnail_from_pdf(pdf_bytes)

    return (
        ContentFile(pdf_bytes, name=f"{data['document_number']}.pdf"),
        ContentFile(thumbnail_buffer.getvalue(), name=f"{data['document_number']}.png"),
    )


def validate_certificate_template(template: dict):
    if not isinstance(template, dict):
        raise ValidationError("Template must be dict")

    if "page_size" not in template or "controls" not in template:
        raise ValidationError("Template must have page_size and controls")

    page_size = template["page_size"]
    if not isinstance(page_size, (list, tuple)) or len(page_size) != 2:
        raise ValidationError("page_size must be [width, height]")

    controls = template["controls"]
    if not isinstance(controls, list):
        raise ValidationError("controls must be list")

    required_types = {"document_number", "completion_title", "recipient_name", "issue_date"}
    control_types = {c.get("type") for c in controls}

    if not required_types.issubset(control_types):
        missing = required_types - control_types
        raise ValidationError(f"Missing required controls: {missing}")

    valid_types = {
        "document_title",
        "document_number",
        "completion_title",
        "completion_period",
        "completion_hours",
        "recipient_name",
        "recipient_birth_date",
        "issuer_name",
        "issue_date",
        "expiration_date",
        "verification_qr",
    }

    for control in controls:
        if control.get("type") not in valid_types:
            raise ValidationError(f"Invalid control type: {control.get('type')}")


def default_certificate_template():
    return {
        "page_size": (210, 297),
        "controls": [
            {
                "type": "document_number",
                "x_percentage": 5,
                "y_percentage": 5,
                "font_size": 9,
                "font_family": "Arial",
                "font_weight": "normal",
                "font_color": "#666666",
                "text_align": "left",
                "label": "",
            },
            {
                "type": "document_title",
                "x_percentage": 50,
                "y_percentage": 18,
                "font_size": 26,
                "font_family": "Arial",
                "font_weight": "bold",
                "font_color": "#000000",
                "text_align": "center",
                "label": "",
            },
            {
                "type": "completion_title",
                "x_percentage": 50,
                "y_percentage": 25,
                "font_size": 16,
                "font_family": "Arial",
                "font_weight": "bold",
                "font_color": "#333333",
                "text_align": "center",
                "label": "",
            },
            {
                "type": "completion_period",
                "x_percentage": 50,
                "y_percentage": 34,
                "font_size": 10,
                "font_family": "Arial",
                "font_weight": "normal",
                "font_color": "#333333",
                "text_align": "center",
                "label": _("Completion Period"),
            },
            {
                "type": "recipient_name",
                "x_percentage": 10,
                "y_percentage": 42,
                "font_size": 10,
                "font_family": "Arial",
                "font_weight": "bold",
                "font_color": "#000000",
                "text_align": "left",
                "label": _("Recipient Name"),
            },
            {
                "type": "recipient_birth_date",
                "x_percentage": 10,
                "y_percentage": 46,
                "font_size": 10,
                "font_family": "Arial",
                "font_weight": "normal",
                "font_color": "#666666",
                "text_align": "left",
                "label": _("Recipient Birth Date"),
            },
            {
                "type": "completion_hours",
                "x_percentage": 10,
                "y_percentage": 50,
                "font_size": 10,
                "font_family": "Arial",
                "font_weight": "normal",
                "font_color": "#333333",
                "text_align": "left",
                "label": _("Completion Hours"),
            },
            {
                "type": "issue_date",
                "x_percentage": 50,
                "y_percentage": 80,
                "font_size": 13,
                "font_family": "Arial",
                "font_weight": "normal",
                "font_color": "#000000",
                "text_align": "center",
                "label": _("Issue Date"),
            },
            {
                "type": "issuer_name",
                "x_percentage": 50,
                "y_percentage": 83,
                "font_size": 18,
                "font_family": "Arial",
                "font_weight": "bold",
                "font_color": "#000000",
                "text_align": "center",
                "label": "",
            },
            {
                "type": "verification_qr",
                "x_percentage": 88,
                "y_percentage": 92,
                "font_size": 0,
                "font_family": "",
                "font_weight": "",
                "font_color": "",
                "text_align": "left",
                "label": "",
            },
        ],
    }
