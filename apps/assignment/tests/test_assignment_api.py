import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.test.client import Client
from mimesis.providers.generic import Generic

from apps.assignment.models import Question
from apps.assignment.tests.factories import AssignmentFactory
from apps.learning.tests.factories import EnrollmentFactory
from conftest import AdminUser


@pytest.mark.e2e
@pytest.mark.django_db
def test_assignment_flow(client: Client, mimesis: Generic, admin_user: AdminUser):
    admin_user.login()

    assignment = AssignmentFactory.create(title=mimesis.text.title())
    EnrollmentFactory(
        content_type=ContentType.objects.get_for_model(assignment),
        content_id=assignment.id,
        active=True,
        user_id=admin_user.id,
    )

    # get assignment session
    res = client.get(f"/api/v1/assignment/{assignment.id}/session")
    assert res.status_code == 200, "get assignment session"

    # otp
    admin_user.setup_otp()
    res = admin_user.verify_otp(token=res.json()["otpToken"])

    # start new assignment attempt
    res = client.post(f"/api/v1/assignment/{assignment.id}/attempt")
    assert res.status_code == 200, "start new assignment attempt"
    attempt = res.json()

    question = Question.objects.get(id=attempt["question"]["id"])
    question.attachment_file_types = ["txt"]
    question.save()

    # create test txt file
    test_file = ContentFile(mimesis.text.text(quantity=10000), name="test.txt")

    # submit assignment
    res = client.post(
        f"/api/v1/assignment/{assignment.id}/attempt/submit",
        data={"answer": mimesis.text.text(), "files": [test_file]},
        format="multipart",
    )
    assert res.status_code == 200, "submit assignment"

    assignment.max_attempts = 2
    assignment.save()

    # deactivate attempt
    res = client.delete(f"/api/v1/assignment/{assignment.id}/attempt/deactivate")
    assert res.status_code == 200, "deactivate attempt"
