import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.exam.tests.factories import ExamFactory


@pytest.mark.django_db
def test_exam():
    ExamFactory.create()


@pytest.mark.load_data
def test_load_exam_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        ExamFactory.create_batch(10)
