import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.discussion.tests.factories import DiscussionFactory


@pytest.mark.django_db
def test_discussion():
    DiscussionFactory.create()


@pytest.mark.load_data
def test_load_discussion_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        DiscussionFactory.create_batch(10)
