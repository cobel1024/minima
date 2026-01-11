import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.competency.tests.factories import BadgeFactory, CertificateFactory, CompetencyGoalFactory


@pytest.mark.django_db
def test_competency():
    BadgeFactory.create()
    CertificateFactory.create()
    CompetencyGoalFactory.create()


@pytest.mark.load_data
def test_load_competency_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        BadgeFactory.create_batch(2)
        CertificateFactory.create_batch(2)
        CompetencyGoalFactory.create_batch(2)
