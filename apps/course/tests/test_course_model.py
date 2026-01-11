import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.course.tests.factories import CourseFactory


@pytest.mark.order(-2)
@pytest.mark.django_db
def test_course():
    CourseFactory.create()


@pytest.mark.order(-2)
@pytest.mark.load_data
def test_load_course_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        CourseFactory.create_batch(10)
