import logging
from typing import TYPE_CHECKING, Sequence, TypedDict

import pghistory
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.files import File
from django.db import connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.models import (
    CASCADE,
    BooleanField,
    Case,
    CharField,
    Count,
    DateTimeField,
    DurationField,
    Field,
    FloatField,
    ForeignKey,
    ImageField,
    Index,
    Model,
    OneToOneField,
    TextChoices,
    TextField,
    UniqueConstraint,
    URLField,
    When,
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import LearningObjectMixin, TimeStampedMixin
from apps.common.util import offset_paginate
from apps.operation.models import AttachmentMixin

User = get_user_model()

log = logging.getLogger(__name__)


WATCH = "1"


class VarBitField(Field):
    def db_type(self, connection: BaseDatabaseWrapper):
        return "varbit"


class MatchedLineDict(TypedDict):
    start: int
    line: str


@pghistory.track()
class Media(LearningObjectMixin):
    class FormatChoices(TextChoices):
        VIDEO = "video", _("Video")
        SHORT = "short", _("Short")
        EBOOK = "ebook", _("Ebook")
        HTML = "html", _("HTML")
        PDF = "pdf", _("PDF")

    thumbnail = ImageField(_("Thumbnail"))
    owner = ForeignKey(User, CASCADE, verbose_name=_("Owner"))
    format = CharField(_("Format"), max_length=30, choices=FormatChoices.choices)
    duration = DurationField(_("Duration"))
    uploaded = BooleanField(_("Uploaded"), default=False)
    url = URLField(_("URL"), max_length=500, unique=True)

    class Meta(LearningObjectMixin.Meta):
        verbose_name = _("Media")
        verbose_name_plural = _("Medias")

    if TYPE_CHECKING:
        pk: str
        subtitle_set: "list[Subtitle]"
        matched_lines: list[MatchedLineDict] | None

    @property
    def duration_seconds(self):
        return self.duration.total_seconds()

    @classmethod
    def annotate_accessible(cls):
        now = timezone.now()
        return cls.objects.annotate(
            accessible=Case(
                When(publicaccessmedia__start__lte=now, publicaccessmedia__archive__gte=now, then=True),
                default=False,
                output_field=BooleanField(),
            )
        )

    @classmethod
    async def search(cls, *, q: str, page: int, size: int):
        from apps.content.documents import document_search

        qs = cls.annotate_accessible().annotate(subtitle_count=Count("subtitle")).select_related("owner")

        if not q:
            searched = None
            paginated = await offset_paginate(qs, page=page, size=size)
        else:
            # document search
            searched = await sync_to_async(document_search)(q=q, page=page, size=size)
            paginated: dict = {
                "items": [m async for m in qs.filter(id__in=searched["lines"].keys())],
                "count": searched["count"],
                "size": size,
                "page": page,
                "pages": searched["pages"],
            }

        for media in paginated["items"]:
            media.matched_lines = searched["lines"][media.pk] if searched else None

        return paginated


@pghistory.track()
class PublicAccessMedia(Model):
    media = OneToOneField(Media, CASCADE, verbose_name=_("Media"))
    start = DateTimeField(_("Start"), default=timezone.now)
    end = DateTimeField(_("End"))
    archive = DateTimeField(_("Archive"))

    class Meta:
        verbose_name = _("Public Access Media")
        verbose_name_plural = _("Public Access Medias")

    @classmethod
    async def get_access_date(cls, *, media_id: str):
        now = timezone.now()
        return await cls.objects.filter(media_id=media_id, start__lte=now, archive__gte=now).afirst()


@pghistory.track()
class Subtitle(Model):
    media = ForeignKey(Media, CASCADE, verbose_name=_("Media"))
    lang = CharField(_("Language"), max_length=10)
    body = TextField(_("Body"))

    class Meta:
        constraints = [UniqueConstraint(fields=["media", "lang"], name="content_subtitle_me_la_uniq")]
        verbose_name = _("Subtitle")
        verbose_name_plural = _("Subtitles")


@pghistory.track(exclude=["last_position"])
class Watch(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    media = ForeignKey(Media, CASCADE, verbose_name=_("Media"))
    last_position = FloatField(_("Last Position"))
    watch_bits = VarBitField(_("Watch Bits"), blank=True, null=True)
    rate = FloatField(_("Watch Rate"))
    passed = BooleanField(_("Passed"), default=False)
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta(TimeStampedMixin.Meta):
        constraints = [UniqueConstraint(fields=["user", "media", "context"], name="content_watch_us_me_co_ke_uniq")]
        verbose_name = _("Watch")
        verbose_name_plural = _("Watches")
        indexes = [Index(fields=["user_id", "context"])]

    if TYPE_CHECKING:
        pk: int
        media_id: str

    @classmethod
    async def update_media_watch(
        cls, *, media_id: str, user_id: str, context: str, last_position: float, watch_bits: str | None
    ):
        def _execute_update():
            if watch_bits is None:
                cls.objects.update_or_create(
                    media_id=media_id, user_id=user_id, context=context, defaults={"last_position": last_position}
                )
                return

            if not watch_bits or set(watch_bits) - {"0", "1"}:
                raise ValueError("watch_bits must be a non-empty bit string")

            bit_length = len(watch_bits)
            bit_count = watch_bits.count(WATCH)

            table = cls._meta.db_table
            media_table = Media._meta.db_table

            sql = f"""
                WITH
                input_bits AS (
                    SELECT '{watch_bits}'::varbit AS bits
                ),
                media_info AS (
                    SELECT passing_point
                    FROM {media_table}
                    WHERE id = %(media_id)s
                ),
                existing AS (
                    SELECT watch_bits FROM {table} WHERE user_id = %(user_id)s AND media_id = %(media_id)s AND context
                    = %(context)s
                ),
                merged AS (
                    SELECT
                        CASE
                            WHEN e.watch_bits IS NULL THEN
                                i.bits
                            WHEN LENGTH(e.watch_bits) < %(bit_length)s THEN
                                RPAD(e.watch_bits::text, %(bit_length)s, '0')::varbit | i.bits
                            WHEN LENGTH(e.watch_bits) > %(bit_length)s THEN
                                SUBSTRING(e.watch_bits, 1, %(bit_length)s) | i.bits
                            ELSE
                                e.watch_bits | i.bits
                        END AS bits
                    FROM input_bits i
                    LEFT JOIN existing e ON true
                ),
                final AS (
                    SELECT bits, BIT_COUNT(bits) AS bit_count
                    FROM merged
                )
                INSERT INTO {table} (
                    user_id, media_id, context, watch_bits, rate, passed, last_position, created, modified
                )
                VALUES (
                    %(user_id)s,
                    %(media_id)s,
                    %(context)s,
                    (SELECT bits FROM input_bits),
                    %(rate)s,
                    %(rate)s >= (SELECT passing_point FROM media_info),
                    %(last_position)s,
                    NOW(),
                    NOW()
                )
                ON CONFLICT (user_id, media_id, context)
                DO UPDATE SET
                    watch_bits = (SELECT bits FROM final),
                    rate = (SELECT bit_count FROM final) * 100.0 / %(bit_length)s,
                    passed = ((SELECT bit_count FROM final) * 100.0 / %(bit_length)s) >= (SELECT passing_point FROM media_info),
                    last_position = EXCLUDED.last_position,
                    modified = NOW();
            """

            params = {
                "media_id": media_id,
                "user_id": user_id,
                "context": context,
                "last_position": last_position,
                # "watch_bits": watch_bits, # large data, to avoid repeating leteral data, use f-string
                "rate": bit_count * 100.0 / bit_length,
                "bit_length": bit_length,
            }

            with connection.cursor() as cursor:
                cursor.execute(sql, params)

        await sync_to_async(_execute_update, thread_sensitive=True)()


@pghistory.track()
class Note(TimeStampedMixin, AttachmentMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    media = ForeignKey(Media, CASCADE, verbose_name=_("Media"))
    note = TextField(verbose_name=_("Note"))
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta(TimeStampedMixin.Meta, AttachmentMixin.Meta):
        constraints = [UniqueConstraint(fields=["user", "media", "context"], name="content_note_us_me_co_keuniq")]
        verbose_name = _("Note")
        verbose_name_plural = _("Notes")

    if TYPE_CHECKING:
        pk: int

    @property
    def cleaned_note(self):
        return self.update_attachment_urls(content=self.note)

    @classmethod
    async def upsert(cls, *, user_id: str, media_id: str, context: str, note: str, files: Sequence[File] | None):
        note_, created = await cls.objects.aupdate_or_create(
            user_id=user_id, media_id=media_id, context=context, defaults={"note": note}
        )
        await note_.update_attachments(files=files, owner_id=user_id, content=note_.note)
        return note_
