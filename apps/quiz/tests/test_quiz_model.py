import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.quiz.tests.factories import QuizFactory


@pytest.mark.django_db
def test_quiz():
    QuizFactory.create()


@pytest.mark.load_data
def test_load_quiz_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        QuizFactory.create_batch(10)
