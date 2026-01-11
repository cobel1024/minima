import math
from datetime import timedelta
from typing import TYPE_CHECKING

import mimesis
from asgiref.sync import async_to_sync
from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone
from factory.declarations import Iterator, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.common.factory import GradeFieldFactory, GradeWorkflowFactory, LearningObjectFactory, dummy_html
from apps.exam.models import Attempt, Exam, Grade, Question, QuestionPool, Solution, Submission, TempAnswer
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

    @lazy_attribute
    def composition(self):
        option = generic.random.choice([(20, 3, 0, 1), (20, 5, 0, 1), (25, 0, 0, 1), (15, 5, 5, 1), (20, 0, 3, 1)])
        composed = {"single_choice": option[0], "text_input": option[1], "number_input": option[2], "essay": option[3]}
        return {k: v for k, v in composed.items() if v != 0}

    if TYPE_CHECKING:
        question_set: QuerySet[Question]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.question_set.exists():
            return

        QuestionFactory.reset_sequence()
        for format, count in self.composition.items():
            QuestionFactory.create_batch(count * 3, pool=self, format=format)


class QuestionFactory(DjangoModelFactory[Question]):
    pool = SubFactory(QuestionPoolFactory)
    format = Iterator(Question.FormatChoices)
    question = Sequence(lambda n: f"{generic.text.text(quantity=generic.random.randint(1, 3))} {n}")
    supplement = LazyFunction(lambda: dummy_html() if generic.random.randint(1, 5) == 1 else "")

    class Meta:
        model = Question
        django_get_or_create = ("pool", "question")
        skip_postgeneration_save = True

    @lazy_attribute
    def options(self) -> list[str]:
        if self.format == Question.FormatChoices.SINGLE_CHOICE.value:
            return [generic.text.text(quantity=generic.random.randint(1, 3)) for _ in range(5)]
        return []

    @lazy_attribute
    def point(self):
        if self.format == Question.FormatChoices.SINGLE_CHOICE.value:
            return 1
        elif self.format == Question.FormatChoices.TEXT_INPUT.value:
            return 3
        elif self.format == Question.FormatChoices.NUMBER_INPUT.value:
            return 3
        else:
            return 10  # essay

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        SolutionFactory.create(question=self)


class SolutionFactory(DjangoModelFactory[Solution]):
    question = SubFactory(QuestionFactory)
    correct_criteria = FactoryField("text")
    explanation = FactoryField("text")
    reference = FactoryField("words", quantity=generic.random.randint(1, 3))

    class Meta:
        model = Solution
        django_get_or_create = ("question",)

    @lazy_attribute
    def correct_answers(self) -> list[str]:
        if self.question.format == Question.FormatChoices.SINGLE_CHOICE.value:
            return [str(generic.random.randint(1, len(self.question.options)))]
        elif self.question.format == Question.FormatChoices.NUMBER_INPUT.value:
            return [str(generic.random.randint(1, 10))]
        return []


class ExamFactory(LearningObjectFactory[Exam], GradeWorkflowFactory[Exam]):
    passing_point = FactoryField("choice", items=[60, 80])
    max_attempts = FactoryField("choice", items=[1, 2])
    verification_required = True

    owner = SubFactory("account.tests.factories.UserFactory")
    honor_code = SubFactory(HonorCodeFactory)
    question_pool = SubFactory(QuestionPoolFactory)
    duration = FactoryField("choice", items=[timedelta(minutes=m) for m in [30, 60]])

    class Meta:
        model = Exam
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        AttemptFactory.create_batch(3, exam=self)


class AttemptFactory(DjangoModelFactory[Attempt]):
    exam = SubFactory(ExamFactory)
    learner = SubFactory("account.tests.factories.UserFactory")
    started = LazyFunction(lambda: timezone.now())
    active = True

    class Meta:
        model = Attempt
        django_get_or_create = ("exam", "learner")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        questions: QuerySet[Question]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        self.questions.set(async_to_sync(self.exam.question_pool.compose_questions)())

        temp_answer = TempAnswerFactory.create(attempt=self)
        SubmissionFactory.create(attempt=self, answers=temp_answer.answers)


class TempAnswerFactory(DjangoModelFactory[TempAnswer]):
    attempt = SubFactory(AttemptFactory)

    class Meta:
        model = TempAnswer
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
            if hasattr(q, "solution") and q.solution.correct_answers:
                if generic.random.weighted_choice({True: 9, False: 1}):
                    answers[str(q.pk)] = q.solution.correct_answers[0]
                else:
                    answers[str(q.pk)] = str(1)
            else:
                if q.format == Question.FormatChoices.ESSAY.value:
                    answers[str(q.pk)] = generic.text.text(quantity=generic.random.randint(1, 3))
                elif q.format == Question.FormatChoices.TEXT_INPUT.value:
                    answers[str(q.pk)] = generic.text.word()
                elif q.format == Question.FormatChoices.NUMBER_INPUT.value:
                    answers[str(q.pk)] = str(generic.random.randint(1, 10))
        return answers


class SubmissionFactory(DjangoModelFactory[Submission]):
    attempt = SubFactory(AttemptFactory)

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

            # subjective questions
            points = grade.attempt.questions.exclude(format=Question.FormatChoices.SINGLE_CHOICE.value).only(
                "pk", "point"
            )
            earned_details: dict[str, int | None] = {str(s.pk): math.ceil(s.point / 2) for s in points}

            # feedback
            feedback: dict[str, str] = {
                q_id: generic.text.text(quantity=generic.random.randint(1, 3)) for q_id in earned_details.keys()
            }
            grade.feedback = feedback

            # grade
            async_to_sync(grade.grade)(earned_existing=earned_details)

            # zero earned
            failed_q_id: list[int] = []
            for q_id, earned in grade.earned_details.items():
                if earned == 0:
                    failed_q_id.append(int(q_id))

            grade.attempt.questions.filter(pk__in=failed_q_id)

        return grade
