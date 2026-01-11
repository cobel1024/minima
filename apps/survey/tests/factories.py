from typing import TYPE_CHECKING

import mimesis
from django.conf import settings
from django.db.models import QuerySet
from django.utils.translation import gettext as _
from factory.declarations import Iterator, LazyAttribute, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.common.factory import LearningObjectFactory, dummy_html
from apps.survey.models import Question, QuestionPaper, Submission, Survey

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class QuestionPaperFactory(DjangoModelFactory[QuestionPaper]):
    title = FactoryField("text.title")
    description = FactoryField("text")
    owner = SubFactory("account.tests.factories.UserFactory")

    class Meta:
        model = QuestionPaper
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        question_set: "QuerySet[Question]"

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.question_set.exists():
            return

        QuestionFactory.reset_sequence()
        QuestionFactory.create_batch(10, paper=self, format=Question.FormatChoices.SINGLE_CHOICE.value)
        QuestionFactory.create_batch(3, paper=self, format=Question.FormatChoices.TEXT_INPUT.value)
        QuestionFactory.create_batch(2, paper=self, format=Question.FormatChoices.NUMBER_INPUT.value)


class QuestionFactory(DjangoModelFactory[Question]):
    ordering = Sequence(lambda n: n)
    paper = SubFactory(QuestionPaperFactory)
    format = Iterator(Question.FormatChoices)
    question = Sequence(lambda n: f"{generic.text.text(quantity=generic.random.randint(1, 3))} {n}")
    supplement = LazyFunction(lambda: dummy_html() if generic.random.randint(1, 5) == 1 else "")
    mandatory = FactoryField("random.weighted_choice", choices={True: 9, False: 1})

    class Meta:
        model = Question

    @lazy_attribute
    def options(self) -> list[str]:
        if self.format == Question.FormatChoices.SINGLE_CHOICE.value:
            return [generic.text.text(quantity=generic.random.randint(1, 3)) for _ in range(5)]
        return []


class SurveyFactory(LearningObjectFactory[Survey]):
    passing_point = 0
    max_attempts = 0
    verification_required = False

    owner = SubFactory("account.tests.factories.UserFactory")
    paper = SubFactory(QuestionPaperFactory)
    complete_message = FactoryField("text")
    anonymous = FactoryField("boolean")

    class Meta:
        model = Survey
        django_get_or_create = ("title",)
        skip_postgeneration_save = True

    @lazy_attribute
    def likert_options(self):
        if generic.random.weighted_choice({True: 7, False: 3}):
            return []
        return [_("Strongly Disagree"), _("Disagree"), _("Neutral"), _("Agree"), _("Strongly Agree")]

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return
        if self.anonymous:
            SubmissionFactory.create_batch(10, survey=self, respondent=None)
        else:
            SubmissionFactory.create_batch(10, survey=self)


class SubmissionFactory(DjangoModelFactory[Submission]):
    survey = SubFactory(SurveyFactory)
    respondent = SubFactory("account.tests.factories.UserFactory")
    hashed_email = LazyAttribute(
        lambda o: Submission.hash_email(o.respondent.email if o.respondent else generic.person.email())
    )
    active = True

    class Meta:
        model = Submission
        django_get_or_create = ("survey", "respondent", "active")

    @lazy_attribute
    def answers(self):

        if self.survey.is_likert:
            return {
                str(pk): generic.random.choice(self.survey.likert_options)
                for pk in self.survey.paper.question_set.values_list("id", flat=True)
            }

        answer_dict = {}
        for q in self.survey.paper.question_set.all():
            if q.format == Question.FormatChoices.SINGLE_CHOICE.value:
                answer = generic.random.randint(1, len(q.options))
            elif q.format == Question.FormatChoices.TEXT_INPUT.value:
                answer = generic.text.word()
            elif q.format == Question.FormatChoices.NUMBER_INPUT.value:
                answer = generic.random.randint(1, 10)
            else:
                raise ValueError(f"Invalid survey question format: {q.format}")

            answer_dict[str(q.pk)] = str(answer)

        return answer_dict
