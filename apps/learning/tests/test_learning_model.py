import mimesis
import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.learning.models import ENROLLABLE_MODELS
from apps.learning.tests.factories import CatalogFactory, EnrollmentFactory
from apps.operation.tests.factories import InquiryFactory
from conftest import AdminUser

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


@pytest.mark.order(-1)
@pytest.mark.django_db
def test_enrollment():
    EnrollmentFactory.create_batch(7)
    CatalogFactory.create_batch(2)


@pytest.mark.order(-1)
@pytest.mark.load_data
def test_load_enrollment_data(db_no_rollback: DjangoDbBlocker, admin_user: AdminUser):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        EnrollmentFactory.create_batch(14)

        user = admin_user.get_user()

        for M in reversed(ENROLLABLE_MODELS):
            for id in M.objects.values_list("id", flat=True)[:3]:
                content_type = ContentType.objects.get_for_model(M)

                # create enrollment
                EnrollmentFactory.create(user=user, content_id=id, content_type=content_type)

                # create inquiry inquiries
                InquiryFactory.create_batch(
                    generic.random.randint(1, 3), writer=user, content_id=id, content_type=content_type
                )

    CatalogFactory.create_batch(2)
