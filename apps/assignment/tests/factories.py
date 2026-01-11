from typing import TYPE_CHECKING

import mimesis
from asgiref.sync import async_to_sync
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from django.utils import timezone
from factory.declarations import Iterator, LazyAttribute, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.enums import DocumentFile
from mimesis.plugins.factory import FactoryField

from apps.account.tests.factories import UserFactory
from apps.assignment.models import (
    Assignment,
    Attempt,
    Grade,
    PerformanceLevel,
    Question,
    QuestionPool,
    Rubric,
    RubricCriterion,
    Solution,
    Submission,
)
from apps.common.factory import GradeFieldFactory, GradeWorkflowFactory, LearningObjectFactory, dummy_html
from apps.operation.tests.factories import HonorCodeFactory

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class RubricFactory(DjangoModelFactory[Rubric]):
    name = FactoryField("text.title")
    description = FactoryField("text")

    class Meta:
        model = Rubric
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        rubriccriterion_set: QuerySet[RubricCriterion]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.rubriccriterion_set.exists():
            return

        RubricCriterionFactory.create_batch(generic.random.randint(3, 5), rubric=self)


class RubricCriterionFactory(DjangoModelFactory[RubricCriterion]):
    rubric = SubFactory(RubricFactory)
    name = FactoryField("text.title")
    description = FactoryField("text")

    class Meta:
        model = RubricCriterion
        django_get_or_create = ("rubric", "name")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        performancelevel_set: QuerySet[PerformanceLevel]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.performancelevel_set.exists():
            return

        for i in range(generic.random.randint(4, 6)):
            PerformanceLevelFactory.create(criterion=self, point=i + 1)


class PerformanceLevelFactory(DjangoModelFactory[PerformanceLevel]):
    criterion = SubFactory(RubricCriterionFactory)
    name = FactoryField("text.title")
    description = FactoryField("text", quantity=3)
    point = Iterator([1, 2, 3, 4, 5])

    class Meta:
        model = PerformanceLevel
        django_get_or_create = ("criterion", "name")
        skip_postgeneration_save = True


class QuestionPoolFactory(DjangoModelFactory[QuestionPool]):
    title = FactoryField("text.title")
    description = FactoryField("text")
    owner = SubFactory(UserFactory)

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
    question = Sequence(lambda n: f"{generic.text.text(quantity=generic.random.randint(1, 3))} {n}")
    supplement = LazyFunction(lambda: dummy_html())
    attachment_file_types = ["docx"]
    sample_attachment = Sequence(
        lambda n: ContentFile(generic.binaryfile.document(file_type=DocumentFile.DOCX), name=f"sample.{n}.docx")
    )
    plagiarism_threshold = FactoryField("choice", items=[80, 100])

    class Meta:
        model = Question
        django_get_or_create = ("pool", "question")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        SolutionFactory.create(question=self)


class SolutionFactory(DjangoModelFactory[Solution]):
    question = SubFactory(QuestionFactory)
    rubric = SubFactory(RubricFactory)
    explanation = FactoryField("text")
    reference = FactoryField("words", quantity=generic.random.randint(1, 3))

    class Meta:
        model = Solution
        django_get_or_create = ("question",)


class AssignmentFactory(LearningObjectFactory[Assignment], GradeWorkflowFactory[Assignment]):
    passing_point = FactoryField("choice", items=[60, 80])
    max_attempts = 1
    verification_required = True

    owner = SubFactory(UserFactory)
    honor_code = SubFactory(HonorCodeFactory)
    question_pool = SubFactory(QuestionPoolFactory)

    class Meta:
        model = Assignment
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        AttemptFactory.create_batch(3, assignment=self)


class AttemptFactory(DjangoModelFactory[Attempt]):
    assignment = SubFactory(AssignmentFactory)
    learner = SubFactory(UserFactory)
    started = LazyFunction(lambda: timezone.now())
    question = LazyAttribute(lambda o: async_to_sync(o.assignment.question_pool.select_question)())
    active = True

    class Meta:
        model = Attempt
        django_get_or_create = ("assignment", "learner")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        SubmissionFactory.create(attempt=self)


class SubmissionFactory(DjangoModelFactory[Submission]):
    attempt = SubFactory(AttemptFactory)
    answer = LazyFunction(lambda: dummy_html())
    extracted_text = LazyAttribute(lambda o: BeautifulSoup(o.answer, "html.parser").get_text(separator=" ", strip=True))

    class Meta:
        model = Submission
        django_get_or_create = ("attempt",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        GradeFactory.create(attempt=self.attempt)


class GradeFactory(GradeFieldFactory[Grade], DjangoModelFactory[Grade]):
    class Meta:
        model = Grade
        django_get_or_create = ("attempt",)
        skip_postgeneration_save = True

    @classmethod
    def create(cls, **kwargs: object):
        try:
            grade = Grade.objects.get(attempt=kwargs["attempt"])
        except Grade.DoesNotExist:
            grade = super().build(**kwargs)

            # earned_details
            attempt = Attempt.objects.select_related("question__solution__rubric", "assignment").get(
                id=grade.attempt_id
            )

            solution = Solution.objects.select_related("rubric").get(question=attempt.question)
            rubric_data = async_to_sync(solution.get_rubric_data)()

            grade.earned_details = {
                criterion["name"]: generic.random.choice([level["point"] for level in criterion["performance_levels"]])
                for criterion in rubric_data["criteria"]
            }

            # fix SynchronousOnlyOperation
            grade.attempt = attempt

            async_to_sync(grade.grade)()

        return grade
