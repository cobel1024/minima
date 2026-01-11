import itertools
from datetime import timedelta
from typing import Type

import mimesis
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from factory.declarations import LazyAttribute, LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.account.tests.factories import UserFactory
from apps.assignment.models import Assignment
from apps.content.models import Media
from apps.course.models import Course
from apps.discussion.models import Discussion
from apps.exam.models import Exam
from apps.learning.models import ENROLLABLE_MODELS, Catalog, CatalogItem, Enrollment, UserCatalog
from apps.survey.models import Survey

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)

ENROLLABLE_FACTORY_MAP: dict[Type, str] = {
    Course: "apps.course.tests.factories.CourseFactory",
    Media: "apps.content.tests.factories.MediaFactory",
    Exam: "apps.exam.tests.factories.ExamFactory",
    Assignment: "apps.assignment.tests.factories.AssignmentFactory",
    Discussion: "apps.discussion.tests.factories.DiscussionFactory",
    Survey: "apps.survey.tests.factories.SurveyFactory",
}


def get_content_type_cycle():
    return itertools.cycle(ENROLLABLE_MODELS)


CONTENT_TYPE_MODEL_CYCLE = get_content_type_cycle()


class EnrollmentFactory(DjangoModelFactory[Enrollment]):
    user = SubFactory("account.tests.factories.UserFactory")
    active = True
    start = LazyFunction(timezone.now)
    end = LazyAttribute(lambda o: o.start + timezone.timedelta(days=30))
    archive = LazyAttribute(lambda o: o.end + timezone.timedelta(days=60))
    enrolled = LazyFunction(timezone.now)

    class Meta:
        model = Enrollment
        django_get_or_create = ("user", "content_type", "content_id")

    @lazy_attribute
    def content_type(self):
        M = next(CONTENT_TYPE_MODEL_CYCLE)
        return ContentType.objects.get_for_model(M)

    @lazy_attribute
    def content_id(self):
        ContentClass = self.content_type.model_class()
        instance = ContentClass.objects.first()

        if not instance:
            factory_path = ENROLLABLE_FACTORY_MAP[ContentClass]
            module_path, class_name = factory_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            FactoryClass = getattr(module, class_name)
            instance = FactoryClass.create()

        return instance.pk


class CatalogFactory(DjangoModelFactory[Catalog]):
    name = FactoryField("text.title")
    description = FactoryField("text")
    active = True
    public = True
    available_from = LazyFunction(lambda: timezone.now())
    available_until = LazyAttribute(lambda o: o.available_from + timedelta(days=90))

    class Meta:
        model = Catalog
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        CatalogItemFactory.create_batch(size=10, catalog=self)


class CatalogItemFactory(DjangoModelFactory[CatalogItem]):
    catalog = SubFactory(CatalogFactory)

    class Meta:
        model = CatalogItem
        django_get_or_create = ("catalog", "content_type", "content_id")
        skip_postgeneration_save = True

    @lazy_attribute
    def content_type(self):
        Model = generic.random.choice(ENROLLABLE_MODELS)
        return ContentType.objects.get_for_model(Model)

    @lazy_attribute
    def content_id(self):
        ContentClass = self.content_type.model_class()
        instance = ContentClass.objects.order_by("?").first()

        if not instance:
            factory_path = ENROLLABLE_FACTORY_MAP[ContentClass]
            module_path, class_name = factory_path.rsplit(".", 1)
            module = __import__(module_path, fromlist=[class_name])
            FactoryClass = getattr(module, class_name)
            instance = FactoryClass.create()

        return instance.pk


class UserCatalogFactory(DjangoModelFactory[UserCatalog]):
    user = SubFactory(UserFactory)
    catalog = SubFactory(CatalogFactory)
    granted_by = SubFactory(UserFactory)
    note = FactoryField("text", quantity=generic.random.randint(1, 3))

    class Meta:
        model = UserCatalog
        django_get_or_create = ("user", "catalog")
