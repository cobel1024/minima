import os
import tempfile

import pytest
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from mimesis.plugins.factory import FactoryField
from openpyxl import Workbook
from pytest_django import DjangoDbBlocker
from tablib import Dataset

from apps.account.tests.factories import UserFactory
from apps.operation.import_export import CategoryResource
from apps.operation.models import Category
from apps.operation.tests.factories import (
    AnnouncementFactory,
    AttachmentFactory,
    FAQFactory,
    HonorCodeFactory,
    InquiryFactory,
    InstructorFactory,
    MessageFactory,
    PolicyFactory,
    ThreadFactory,
    isced_sample_category,
)
from conftest import AdminUser


@pytest.mark.django_db
def test_announcement():
    AnnouncementFactory.create()


@pytest.mark.load_data
def test_load_announcement_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        AnnouncementFactory.create_batch(30)


@pytest.mark.django_db
def test_instructor():
    InstructorFactory.create()


@pytest.mark.load_data
def test_load_instructor_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        InstructorFactory.create_batch(3)


@pytest.mark.django_db
def test_honor_code():
    HonorCodeFactory.create()


@pytest.mark.load_data
def test_load_honor_code_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        HonorCodeFactory.create_batch(3)


@pytest.mark.django_db
def test_faq():
    FAQFactory.create()


@pytest.mark.load_data
def test_load_faq_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        FAQFactory.create_batch(3)


@pytest.mark.django_db
def test_attachment(admin_user: AdminUser):
    AttachmentFactory.create(owner=admin_user.get_user())


@pytest.mark.django_db
def test_inquiry():
    InquiryFactory.create(content=UserFactory.create())


@pytest.mark.django_db
def test_category_resource_import_data():
    Category.objects.all().delete()

    test_data = [["name", "ancestors"], ["root1", ""], ["root2", ""], ["sub1", "root1"], ["leaf1", "root1,sub1"]]

    wb = Workbook()
    ws = wb.active or wb.create_sheet()

    for row_data in test_data:
        ws.append(row_data)

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_file:
        wb.save(tmp_file.name)
        tmp_filename = tmp_file.name

    try:
        with open(tmp_filename, "rb") as f:
            dataset = Dataset().load(f.read(), format="xlsx", headers=True)

        resource = CategoryResource()
        resource.import_data(dataset, dry_run=False)

        assert Category.objects.count() == 4

        root1 = Category.objects.filter(name="root1", ancestors=[]).first()
        assert root1 is not None
        assert root1.depth == 1

        sub1 = Category.objects.filter(name="sub1", ancestors=["root1"]).first()
        assert sub1 is not None
        assert sub1.depth == 2

        leaf1 = Category.objects.filter(name="leaf1", ancestors=["root1", "sub1"]).first()
        assert leaf1 is not None
        assert leaf1.depth == 3

    finally:
        os.unlink(tmp_filename)


@pytest.mark.django_db
def test_category():
    isced_sample_category()


@pytest.mark.load_data
def test_load_category_data(db_no_rollback: DjangoDbBlocker):
    isced_sample_category()


@pytest.mark.django_db
def test_message():
    MessageFactory.create_batch(10)


@pytest.mark.load_data
def test_load_message_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        MessageFactory.create_batch(10)


@pytest.mark.django_db
def test_policy():
    PolicyFactory.create()


@pytest.mark.load_data
def test_load_policy_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        PolicyFactory.create_batch(5)


@pytest.mark.django_db
def test_thread():
    subject = UserFactory.create()
    ThreadFactory.create(subject_type=ContentType.objects.get_for_model(subject), subject_id=subject.pk)


@pytest.mark.load_data
def test_load_thread_data(db_no_rollback: DjangoDbBlocker):
    users = UserFactory.create_batch(10)
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        for user in users:
            ThreadFactory.create(subject_type=ContentType.objects.get_for_model(user), subject_id=user.pk)
