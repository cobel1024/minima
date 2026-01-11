import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.survey.tests.factories import SurveyFactory


@pytest.mark.django_db
def test_survey():
    SurveyFactory.create()


@pytest.mark.load_data
def test_load_survey_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        SurveyFactory.create_batch(10)
