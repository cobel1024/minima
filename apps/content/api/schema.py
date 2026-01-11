from typing import Annotated, Literal

from pydantic.fields import Field

from apps.account.api.schema import OwnerSchema
from apps.common.schema import LearningObjectMixinSchema, Schema, TimeStampedMixinSchema
from apps.content.api.encoder import GzipInEncodedType, GzipOutEncodedType
from apps.content.models import Note


class MediaSchema(LearningObjectMixinSchema):
    id: str
    thumbnail: str
    duration_seconds: float
    owner: OwnerSchema
    subtitle_count: int
    format: Literal["video", "short", "ebook", "html", "pdf"]
    uploaded: bool
    url: str


class SubtitleSchema(Schema):
    id: int
    lang: str
    body: str


class WatchOutSchema(Schema):
    last_position: float
    watch_bits: Annotated[GzipOutEncodedType | None, Field(None, description="Gzip compressed Bit String")]


class WatchInSchema(Schema):
    last_position: float
    watch_bits: Annotated[GzipInEncodedType, Field(None, description="Gzip compressed Bit String")]


class NoteSchema(TimeStampedMixinSchema):
    id: int
    note: str

    @staticmethod
    def resolve_note(obj: Note):
        return obj.cleaned_note


class NoteSaveSchema(Schema):
    note: Annotated[str, Field(..., max_length=10000)]


class SearchedMediaSchema(MediaSchema):
    class MatchedLineSchema(Schema):
        start: str
        line: str

    accessible: bool
    matched_lines: list[MatchedLineSchema] | None
