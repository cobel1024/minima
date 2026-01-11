import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.account.tests.factories import UserFactory


@pytest.mark.django_db
def test_user():
    UserFactory.create()


@pytest.mark.load_data
def test_load_user_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        UserFactory.create_batch(100)
