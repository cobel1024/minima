from typing import TYPE_CHECKING

import mimesis
from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from factory.declarations import LazyAttribute, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.common.factory import GradeFieldFactory, LearningObjectFactory, dummy_html
from apps.quiz.models import Attempt, Grade, Question, QuestionPool, Quiz, Solution, Submission

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import ManyRelatedManager


class QuestionPoolFactory(DjangoModelFactory[QuestionPool]):
    title = FactoryField("text.title")
    description = FactoryField("text")
    owner = SubFactory("account.tests.factories.UserFactory")
    select_count = FactoryField("choice", items=[3, 5])

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
        QuestionFactory.create_batch(self.select_count * 3, pool=self)


class QuestionFactory(DjangoModelFactory[Question]):
    pool = SubFactory(QuestionPoolFactory)
    question = Sequence(lambda n: f"{generic.text.text(quantity=generic.random.randint(1, 3))} {n}")
    supplement = LazyFunction(lambda: dummy_html() if generic.random.randint(1, 5) == 1 else "")
    options = LazyFunction(lambda: [generic.text.text(quantity=generic.random.randint(1, 3)) for _ in range(5)])
    point = 1

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
    correct_answers = LazyAttribute(lambda o: [str(generic.random.randint(1, len(o.question.options)))])
    explanation = FactoryField("text")

    class Meta:
        model = Solution
        django_get_or_create = ("question",)


class QuizFactory(LearningObjectFactory[Quiz]):
    passing_point = FactoryField("choice", items=[60, 80])
    max_attempts = FactoryField("choice", items=[1, 2])
    verification_required = False

    owner = SubFactory("account.tests.factories.UserFactory")
    question_pool = SubFactory(QuestionPoolFactory)

    class Meta:
        model = Quiz
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        AttemptFactory.create_batch(3, quiz=self)


class AttemptFactory(DjangoModelFactory[Attempt]):
    quiz = SubFactory(QuizFactory)
    learner = SubFactory("account.tests.factories.UserFactory")
    started = LazyFunction(lambda: timezone.now())
    active = True

    class Meta:
        model = Attempt
        django_get_or_create = ("quiz", "learner")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        questions: ManyRelatedManager

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        self.questions.set(self.quiz.question_pool.select_questions())

        SubmissionFactory.create(attempt=self)


class SubmissionFactory(DjangoModelFactory[Submission]):
    attempt = SubFactory(AttemptFactory)

    class Meta:
        model = Submission
        django_get_or_create = ("attempt",)
        skip_postgeneration_save = True

    @lazy_attribute
    def answers(self):
        # cunning paper

        cunning_paper = Question.objects.select_related("solution").filter(
            id__in=self.attempt.questions.values_list("id", flat=True)
        )

        answers: dict[str, str] = {}
        for q in cunning_paper:
            if generic.random.weighted_choice({True: 9, False: 1}):
                answers[str(q.pk)] = q.solution.correct_answers[0]
            else:
                answers[str(q.pk)] = str(1)
        return answers

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
            grade.grade()

            # zero earned
            failed_q_id: list[int] = []
            for q_id, earned in grade.earned_details.items():
                if earned == 0:
                    failed_q_id.append(int(q_id))

            grade.attempt.questions.filter(pk__in=failed_q_id)

        return grade
