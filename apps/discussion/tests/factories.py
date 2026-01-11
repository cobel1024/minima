from typing import TYPE_CHECKING, Callable

import mimesis
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from django.utils import timezone
from factory.declarations import LazyAttribute, LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.plugins.factory import FactoryField

from apps.common.factory import GradeFieldFactory, GradeWorkflowFactory, LearningObjectFactory, dummy_html
from apps.discussion.models import Attempt, Discussion, Grade, Post, Question, QuestionPool
from apps.operation.tests.factories import HonorCodeFactory

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class QuestionPoolFactory(DjangoModelFactory[QuestionPool]):
    title = FactoryField("text.title")
    description = FactoryField("text")
    owner = SubFactory("account.tests.factories.UserFactory")

    class Meta:
        model = QuestionPool
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        question_set: QuerySet[Question]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.question_set.exists():
            return

        QuestionFactory.reset_sequence()
        QuestionFactory.create_batch(3, pool=self)


class QuestionFactory(DjangoModelFactory[Question]):
    pool = SubFactory(QuestionPoolFactory)
    directive = LazyFunction(
        lambda: "\n\n".join([generic.text.text(quantity=generic.random.randint(2, 6)) for _ in range(3)])
    )
    supplement = LazyFunction(lambda: dummy_html())
    point_requirements = FactoryField(
        "choice",
        items=[
            {"post": 2, "reply": 2, "tutor_assessment": 2, "post_min_characters": 200, "reply_min_characters": 100},
            {"post": 1, "reply": 3, "tutor_assessment": 2, "post_min_characters": 200, "reply_min_characters": 100},
        ],
    )

    class Meta:
        model = Question
        django_get_or_create = ("pool", "directive")
        skip_postgeneration_save = True


class DiscussionFactory(LearningObjectFactory[Discussion], GradeWorkflowFactory[Discussion]):
    passing_point = 100
    max_attempts = 1
    verification_required = True

    owner = SubFactory("account.tests.factories.UserFactory")
    honor_code = SubFactory(HonorCodeFactory)
    question_pool = SubFactory(QuestionPoolFactory)

    class Meta:
        model = Discussion
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        AttemptFactory.create_batch(3, discussion=self)


class AttemptFactory(DjangoModelFactory[Attempt]):
    discussion = SubFactory(DiscussionFactory)
    learner = SubFactory("account.tests.factories.UserFactory")
    started = LazyFunction(lambda: timezone.now())
    question = LazyAttribute(lambda o: async_to_sync(o.discussion.question_pool.select_question)())
    active = True

    class Meta:
        model = Attempt
        django_get_or_create = ("discussion", "learner")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        # Posts
        PostFactory.create_batch(2, attempt=self)

        # replies
        parents = Post.objects.filter(parent__isnull=True, attempt__question=self.question).exclude(
            attempt__learner=self.learner
        )[:2]

        for parent in parents:
            PostFactory.create_batch(2, attempt=self, parent=parent)

        # grade
        GradeFactory.create(attempt=self)


class PostFactory(DjangoModelFactory[Post]):
    attempt = SubFactory(AttemptFactory)
    title = FactoryField("text.title")
    body = LazyFunction(
        lambda: "\n\n".join([
            generic.text.text(quantity=generic.random.randint(3, 8)) for _ in range(generic.random.randint(1, 3))
        ])
    )

    class Meta:
        model = Post
        django_get_or_create = ("attempt", "title")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        update_attachments: Callable

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if generic.random.randint(1, 4) == 1:
            files = [
                ContentFile(
                    generic.binaryfile.image(file_type=mimesis.ImageFile.PNG),
                    f"attachment.{generic.random.randint(0, 1000)}.png",
                )
            ]

            async_to_sync(self.update_attachments)(files=files, owner_id=self.attempt.learner.pk, content=self.body)


class GradeFactory(GradeFieldFactory[Grade], DjangoModelFactory[Grade]):
    class Meta:
        model = Grade
        django_get_or_create = ("attempt",)

    @classmethod
    def create(cls, **kwargs: object):
        try:
            grade = Grade.objects.get(attempt=kwargs["attempt"])
        except Grade.DoesNotExist:
            grade = super().build(**kwargs)
            async_to_sync(grade.grade)()

        return grade
