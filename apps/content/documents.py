import math
import re
from collections import OrderedDict
from typing import TypedDict

from django.conf import settings
from django_opensearch_dsl import fields
from django_opensearch_dsl.documents import Document
from django_opensearch_dsl.registries import registry
from opensearchpy import Q

from apps.content.models import MatchedLineDict, Media, Subtitle


@registry.register_document
class MediaDocument(Document):
    media_id = fields.KeywordField(index=False)
    thumbnail = fields.KeywordField(index=False)
    url = fields.KeywordField(index=False)
    title = fields.TextField(analyzer=settings.OPENSEARCH_TEXT_ANALYZER)
    description = fields.TextField(analyzer=settings.OPENSEARCH_TEXT_ANALYZER)
    suggest = fields.CompletionField(analyzer="keyword", search_analyzer="keyword")

    class Index:
        name = "content_media"
        settings = settings.OPENSEARCH_DSL_SETTINGS

    class Django:
        model = Media

    def prepare_media_id(self, instance: Media):
        return instance.pk

    def prepare_suggest(self, instance: Media):
        all_inputs = set()
        all_inputs.add(instance.title)
        title_words = instance.title.split()
        for word in title_words:
            if len(word) >= 2:
                all_inputs.add(word)
        if instance.description:
            all_inputs.add(instance.description)
            desc_words = instance.description.split()
            for word in desc_words:
                if len(word) >= 2:
                    all_inputs.add(word)
        return {"input": list(all_inputs), "weight": 1}

    def prepare_thumbnail(self, instance: Media):
        return instance.thumbnail.url if instance.thumbnail else ""


BLOCK_SEPARATOR = re.compile(r"\n\s*\n")
TIMESTAMP_PATTERN = re.compile(r"(\d{2}:\d{2}:\d{2})\.\d{3} --> (\d{2}:\d{2}:\d{2})\.\d{3}")
LINE_BREAK_PATTERN = re.compile(r"\r\n|\r")


@registry.register_document
class SubtitleDocument(Document):
    media_id = fields.KeywordField()
    lang = fields.KeywordField(index=False)
    body = fields.NestedField(
        properties={
            "start": fields.KeywordField(index=False),
            "line": fields.TextField(analyzer=settings.OPENSEARCH_TEXT_ANALYZER),
        }
    )
    suggest = fields.CompletionField(analyzer="keyword", search_analyzer="keyword")

    class Index:
        name = "content_subtitle"
        settings = settings.OPENSEARCH_DSL_SETTINGS

    class Django:
        model = Subtitle

    def prepare_body(self, instance: Subtitle):
        parsed_subtitles = self.split_webvtt(instance.body)
        return [{"start": parsed["start"], "line": parsed["line"]} for parsed in parsed_subtitles]

    def prepare_suggest(self, instance: Subtitle):
        from collections import Counter

        parsed_subtitles = self.split_webvtt(instance.body)
        word_count = Counter()
        sentences = []

        for parsed in parsed_subtitles:
            line = parsed["line"].strip()
            if len(line) >= 5:
                sentences.append(line)
                for word in line.split():
                    if len(word) >= 2:
                        word_count[word] += 1

        unique_words = list(word_count.keys())
        short_sentences = sorted(sentences, key=len)[:100]

        return {"input": unique_words + short_sentences, "weight": 1}

    @staticmethod
    def split_webvtt(body: str):
        blocks = re.split(BLOCK_SEPARATOR, LINE_BREAK_PATTERN.sub("\n", body))
        captions: list[dict[str, str]] = []
        for block in blocks:
            if not block:
                continue
            splitted = block.split("\n")
            if len(splitted) >= 2:
                timestamp = splitted[0]
                line = " ".join(splitted[1:])
                match = re.match(TIMESTAMP_PATTERN, timestamp)
                if match:
                    start_time = match.group(1)
                    end_time = match.group(2)
                    captions.append({"start": start_time, "end": end_time, "line": line})
        return captions


def get_search_suggestion(*, q: str, limit: int = 10):
    fetch_size = min(limit, 10)

    media_search = MediaDocument.search()
    media_search = media_search.suggest(
        "media_suggest", q, completion={"field": "suggest", "size": fetch_size, "skip_duplicates": True}
    )

    subtitle_search = SubtitleDocument.search()
    subtitle_search = subtitle_search.suggest(
        "subtitle_suggest", q, completion={"field": "suggest", "size": fetch_size, "skip_duplicates": True}
    )

    media_response = media_search.execute()
    subtitle_response = subtitle_search.execute()

    suggestions = []
    seen = set()

    if hasattr(media_response.suggest, "media_suggest"):
        for option in media_response.suggest.media_suggest[0].options:
            text = option.text.strip()
            if text and text not in seen:
                suggestions.append(text)
                seen.add(text)

    if hasattr(subtitle_response.suggest, "subtitle_suggest"):
        for option in subtitle_response.suggest.subtitle_suggest[0].options:
            text = option.text.strip()
            if text and text not in seen:
                suggestions.append(text)
                seen.add(text)
                if len(suggestions) >= limit:
                    break

    return suggestions[:limit]


class SearchResultDict(TypedDict):
    lines: dict[str, list[MatchedLineDict] | None]
    count: int
    pages: int


def document_search(*, q: str, page: int, size: int) -> SearchResultDict:
    offset = (page - 1) * size

    media_search = MediaDocument.search()
    media_search = media_search.query("multi_match", query=q, fields=["title^2", "description"])
    media_search = media_search[offset : offset + size]
    media_response = media_search.execute()

    subtitle_search = SubtitleDocument.search()
    subtitle_search = subtitle_search.query(
        "nested",
        path="body",
        query=Q("match", body__line=q),
        inner_hits={"sort": [{"body.start": {"order": "asc"}}], "size": 6},
    )
    subtitle_search = subtitle_search[offset : offset + size]
    subtitle_response = subtitle_search.execute()

    lines: OrderedDict[str, list[MatchedLineDict] | None] = OrderedDict()

    for hit in media_response:
        if hit.media_id:
            lines[hit.media_id] = None

    for hit in subtitle_response:
        if not hit.media_id:
            continue
        matched_lines: list[MatchedLineDict] = []
        if hasattr(hit.meta, "inner_hits") and "body" in hit.meta.inner_hits:
            for inner_hit in hit.meta.inner_hits.body:
                matched_lines.append({"start": inner_hit.start, "line": inner_hit.line})
        lines[hit.media_id] = matched_lines

    lines = OrderedDict(list(lines.items())[:size])
    total_count = len(lines)

    return SearchResultDict(lines=lines, count=total_count, pages=math.ceil(total_count / size))
