from datetime import timedelta

import mimesis
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.utils import timezone
from factory.declarations import LazyAttribute, LazyFunction, SubFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.common.factory import DjangoModelFactory, LearningObjectFactory, dummy_html
from apps.content.models import Media, Note, PublicAccessMedia, Watch

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class MediaFactory(LearningObjectFactory[Media]):
    passing_point = 80
    max_attempts = 0
    verification_required = False

    owner = SubFactory("account.tests.factories.UserFactory")
    format = FactoryField("choice", items=[Media.FormatChoices.VIDEO, Media.FormatChoices.PDF])
    duration = FactoryField("choice", items=[timedelta(minutes=m) for m in [10, 20, 30, 40]])
    uploaded = LazyFunction(lambda: generic.random.weighted_choice({True: 9, False: 1}))

    @lazy_attribute
    def url(self):
        if self.format == Media.FormatChoices.PDF:
            return staticfiles_storage.url(f"sample/sample.pdf?p={generic.random.randint(0, 7)}")

        elif self.format == Media.FormatChoices.VIDEO:
            return f"https://cdn.plyr.io/static/demo/View_From_A_Blue_Moon_Trailer-576p.mp4?p={generic.random.randint(0, 7)}"

    class Meta:
        model = Media
        django_get_or_create = ("url",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        WatchFactory.create(user=self.owner, media=self)
        NoteFactory.create(user=self.owner, media=self)

        if generic.random.randint(0, 1):
            PublicAccessMediaFactory.create(media=self)


class PublicAccessMediaFactory(DjangoModelFactory[PublicAccessMedia]):
    media = SubFactory(MediaFactory)
    start = LazyFunction(lambda: timezone.now())
    end = LazyFunction(lambda: timezone.now() + timedelta(days=30))
    archive = LazyFunction(lambda: timezone.now() + timedelta(days=60))

    class Meta:
        model = PublicAccessMedia
        django_get_or_create = ("media",)


WATCH = "1"
UNWATCH = "0"


class WatchFactory(DjangoModelFactory[Watch]):
    user = SubFactory("account.tests.factories.UserFactory")
    media = SubFactory(MediaFactory)

    class Meta:
        model = Watch
        django_get_or_create = ("user", "media")

    @lazy_attribute
    def watch_bits(self):

        bits = UNWATCH * int(self.media.duration.total_seconds())
        return bits.replace(UNWATCH, WATCH, generic.random.randint(0, len(bits) - 1))

    last_position = LazyAttribute(lambda o: o.watch_bits.count(WATCH))

    @lazy_attribute
    def rate(self):
        watch_bits = str(self.watch_bits)
        return watch_bits.count(WATCH) / len(watch_bits) * 100.0


class NoteFactory(DjangoModelFactory[Note]):
    user = SubFactory("account.tests.factories.UserFactory")
    media = SubFactory(MediaFactory)
    note = LazyFunction(lambda: dummy_html())

    class Meta:
        model = Note
        django_get_or_create = ("user", "media")
