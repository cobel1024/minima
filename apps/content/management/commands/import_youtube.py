import html
import os
import random
import re
import time
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

import yt_dlp
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.text import Truncator
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled
from youtube_transcript_api.formatters import WebVTTFormatter

from apps.content.models import Media, PublicAccessMedia, Subtitle

User = get_user_model()


class Command(BaseCommand):
    help = "Import YouTube videos or playlists using yt-dlp"

    def __init__(self):
        super().__init__()
        self.stats = {"success": [], "skipped": [], "failed": []}

    def add_arguments(self, parser):
        parser.add_argument("url_or_id", type=str, help="YouTube video/playlist URL or ID")
        parser.add_argument("--owner", type=str, required=True, help="Owner email or ID")
        parser.add_argument("--force-update", action="store_true", help="Force update existing content")

    def handle(self, *args, **options):
        url_or_id = options["url_or_id"]
        owner_identifier = options["owner"]
        force_update = options["force_update"]

        owner = self.get_owner(owner_identifier)
        if not owner:
            self.stdout.write(self.style.ERROR(f"Owner not found: {owner_identifier}"))
            return

        url = self.normalize_url(url_or_id)

        if self.is_playlist(url):
            self.import_playlist(url, owner, force_update)
        else:
            self.import_video(url, owner, force_update)

        self.print_report()

    def get_owner(self, identifier):
        if identifier.isdigit():
            return User.objects.filter(pk=identifier).first()
        return User.objects.filter(email=identifier).first()

    def normalize_url(self, url_or_id):
        if url_or_id.startswith("http"):
            return url_or_id

        if url_or_id.startswith("PL"):
            return f"https://www.youtube.com/playlist?list={url_or_id}"

        return f"https://www.youtube.com/watch?v={url_or_id}"

    def is_playlist(self, url):
        return "playlist" in url or "list=" in url

    def import_video(self, url, owner, force_update):
        info = self.retry_operation(lambda: self.get_video_info(url), f"Video info: {url}")
        if not info:
            return

        media = self.create_media(info, owner, force_update)
        if media:
            self.create_subtitles(media, info, force_update)
            self.stats["success"].append(f"Video: {media.title}")
            self.stdout.write(self.style.SUCCESS(f"Created media: {media.title}"))

    def import_playlist(self, url, owner, force_update):
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}

        playlist_info = self.retry_operation(lambda: self.get_info_with_ydl(url, ydl_opts), f"Playlist info: {url}")
        if not playlist_info:
            return

        for idx, entry in enumerate(playlist_info.get("entries", []), start=1):
            video_url = f"https://www.youtube.com/watch?v={entry['id']}"

            video_info = self.retry_operation(lambda: self.get_video_info(video_url), f"Video info: {video_url}")
            if not video_info:
                continue

            media = self.create_media(video_info, owner, force_update)
            if not media:
                continue

            self.create_subtitles(media, video_info, force_update)

            self.stdout.write(f"  Added: {media.title}")

        self.stats["success"].append(f"Playlist: {playlist_info.get('title', 'Unknown')}")
        self.stdout.write(self.style.SUCCESS(f"Completed playlist: {playlist_info.get('title', 'Unknown')}"))

    def get_video_info(self, url):
        available_langs = [lang[0] for lang in settings.LANGUAGES]

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "writesubtitles": True,
            "writeautomaticsub": True,
            "subtitleslangs": available_langs,
            "subtitlesformat": "vtt",
            "skip_download": True,
            "sleep_interval": 10,
            "max_sleep_interval": 20,
            "sleep_subtitles": 15,
        }

        return self.get_info_with_ydl(url, ydl_opts)

    def get_info_with_ydl(self, url, ydl_opts):
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def create_media(self, info, owner, force_update):
        video_id = info.get("id")
        url = f"https://www.youtube.com/watch?v={video_id}"

        media = Media.objects.filter(url=url).first()

        if media and not force_update:
            self.stdout.write(self.style.WARNING(f"Media already exists: {media.title}"))
            self.stats["skipped"].append(f"Media: {media.title}")
            return media

        if media and force_update:
            media.title = info.get("title", "Untitled")
            media.description = Truncator(info.get("description", "")).chars(5000)
            media.format = self.detect_format(info)
            media.duration = timedelta(seconds=info.get("duration", 0))
            media.save()

            return media

        thumbnail_file = self.retry_operation(
            lambda: self.download_thumbnail(info), f"Thumbnail: {info.get('title', 'Unknown')}"
        )

        media = Media.objects.create(
            url=url,
            owner=owner,
            title=info.get("title", "Untitled"),
            description=Truncator(info.get("description", "")).chars(5000),
            format=self.detect_format(info),
            duration=timedelta(seconds=info.get("duration", 0)),
            uploaded=True,
            thumbnail=thumbnail_file,
        )

        if random.choice([True, False]):
            now = timezone.now()
            PublicAccessMedia.objects.get_or_create(
                media=media, start=now, end=now + timedelta(days=30), archive=now + timedelta(days=90)
            )

        return media

    def download_thumbnail(self, info):
        thumbnails = info.get("thumbnails", [])

        medium_thumbnail = None
        for thumb in thumbnails:
            if thumb.get("id") in ["hq720", "sd", "hqdefault", "mqdefault"]:
                medium_thumbnail = thumb.get("url")
                break

        if not medium_thumbnail and thumbnails:
            sorted_thumbs = sorted(thumbnails, key=lambda x: x.get("width", 0) * x.get("height", 0))
            mid_index = len(sorted_thumbs) // 2
            medium_thumbnail = sorted_thumbs[mid_index].get("url")

        if medium_thumbnail:
            with urllib.request.urlopen(medium_thumbnail) as response:
                image_data = response.read()

            video_id = info.get("id")

            parsed_url = urlparse(medium_thumbnail)
            path = parsed_url.path
            ext = os.path.splitext(path)[1] or ".jpg"

            filename = f"{video_id}{ext}"

            return ContentFile(image_data, name=filename)

        return None

    def detect_format(self, info):
        duration = info.get("duration", 0)
        if duration <= 60:
            return Media.FormatChoices.SHORT
        return Media.FormatChoices.VIDEO

    def create_subtitles(self, media, info, force_update):
        ytt_api = YouTubeTranscriptApi()
        language_codes = [lang[0] for lang in settings.LANGUAGES]

        try:
            transcript_list = ytt_api.list(info.get("id"))
        except TranscriptsDisabled:
            self.stdout.write(self.style.WARNING(f"Transcripts disabled for video: {media.title}"))
            return

        formatter = WebVTTFormatter()

        for transcript in transcript_list:
            if transcript.language_code not in language_codes:
                continue

            existing = Subtitle.objects.filter(media=media, lang=transcript.language_code).exists()
            if existing and not force_update:
                self.stdout.write(f"  Skipping existing subtitle: {transcript.language_code}")
                continue

            fetched = self.retry_operation(
                lambda: transcript.fetch(),
                f"Subtitle {transcript.language_code}: {media.title}",
                max_retries=1,  # maybe blocked by YouTube
                base_delay=5,
            )

            if fetched:
                content = formatter.format_transcript(fetched)
                if content:
                    _, created = Subtitle.objects.update_or_create(
                        media=media, lang=transcript.language_code, defaults={"body": content}
                    )
                    self.stdout.write(f"{'Updated' if created else 'Added'} subtitle: {transcript.language_code}")

    @staticmethod
    def clean_webvtt_content(content: str):
        webvtt_timestamp_tag = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>")
        webvtt_voice_tag = re.compile(r"</?[vciburlang][^>]*>")

        content = webvtt_timestamp_tag.sub("", content)
        content = webvtt_voice_tag.sub("", content)
        content = html.unescape(content)

        return content

    def retry_operation(self, operation, description, max_retries=3, base_delay=1):
        for attempt in range(1, max_retries + 1):
            result = None
            error = None

            try:
                result = operation()
            except Exception as e:
                error = e

            if error is None:
                return result

            if attempt < max_retries:
                delay = base_delay * (2 ** (attempt - 1))
                self.stdout.write(
                    self.style.WARNING(
                        f"Attempt {attempt}/{max_retries} failed for {description}: {str(error)}. Retrying in {delay}s..."
                    )
                )
                time.sleep(delay)
            else:
                self.stdout.write(
                    self.style.ERROR(f"Failed after {max_retries} attempts for {description}: {str(error)}")
                )
                self.stats["failed"].append(f"{description}: {str(error)}")
                return None

    def print_report(self):
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS(f"Success: {len(self.stats['success'])}"))
        for item in self.stats["success"]:
            self.stdout.write(f"  ✓ {item}")

        self.stdout.write(self.style.WARNING(f"\nSkipped: {len(self.stats['skipped'])}"))
        for item in self.stats["skipped"]:
            self.stdout.write(f"  - {item}")

        self.stdout.write(self.style.ERROR(f"\nFailed: {len(self.stats['failed'])}"))
        for item in self.stats["failed"]:
            self.stdout.write(f"  ✗ {item}")

        self.stdout.write("=" * 50)
