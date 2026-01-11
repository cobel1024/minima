import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.partner.tests.factories import CohortFactory, PartnerFactory


@pytest.mark.django_db
def test_partner():
    PartnerFactory.create()
    CohortFactory.create()


@pytest.mark.load_data
def test_load_partner_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        PartnerFactory.create_batch(10)
        CohortFactory.create_batch(10)
