import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.content.tests.factories import MediaFactory
from conftest import AdminUser


@pytest.mark.django_db
def test_media():
    MediaFactory.create()


@pytest.mark.load_data
def test_load_media_data(db_no_rollback: DjangoDbBlocker, admin_user: AdminUser):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        MediaFactory.create_batch(40)
