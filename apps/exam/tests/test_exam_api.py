import json
from typing import cast

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test.client import Client
from django.utils import timezone
from mimesis.providers.generic import Generic

from apps.exam.models import Exam, Grade
from apps.exam.tests.factories import ExamFactory
from apps.learning.tests.factories import EnrollmentFactory
from conftest import AdminUser


@pytest.mark.e2e
@pytest.mark.django_db
def test_exam_flow(client: Client, mimesis: Generic, admin_user: AdminUser):
    admin_user.login()

    exam = cast(Exam, ExamFactory())
    EnrollmentFactory(
        content_type=ContentType.objects.get_for_model(exam), content_id=exam.id, active=True, user_id=admin_user.id
    )

    # get exam session
    res = client.get(f"/api/v1/exam/{exam.id}/session")
    assert res.status_code == 200, "get exam session"

    # otp
    admin_user.setup_otp()
    res = admin_user.verify_otp(token=res.json()["otpToken"])

    # start new exam attempt
    res = client.post(f"/api/v1/exam/{exam.id}/attempt")
    assert res.status_code == 200, "start new exam attempt"
    attempt_id = res.json()["id"]

    answers: dict[str, str] = {}

    for question in res.json()["questions"]:
        format = question["format"]
        id_str = str(question["id"])
        if format == "single_choice":
            # sample question
            answers[id_str] = str(mimesis.random.randint(1, len(question["options"] or [])))
        elif format == "text_input":
            answers[id_str] = mimesis.text.word()
        elif format == "number_input":
            answers[id_str] = str(mimesis.random.randint(1, 2))
        elif format == "essay":
            answers[id_str] = mimesis.text.text()
        else:
            raise ValueError(f"Invalid question format: {format}")

    # save answers
    res = client.post(f"/api/v1/exam/{exam.id}/attempt/save", data=json.dumps(answers), content_type="application/json")
    assert res.status_code == 200, "save answers"

    # get exam session again
    res = client.get(f"/api/v1/exam/{exam.id}/session")
    assert res.status_code == 200, "get exam attempt again"
    assert res.json()["attempt"]["savedAnswers"] == answers, "get exam attempt again"

    # submit exam
    res = client.post(
        f"/api/v1/exam/{exam.id}/attempt/submit", data=json.dumps(answers), content_type="application/json"
    )
    assert res.status_code == 200, "submit exam"

    # admin set grade completed
    Grade.objects.filter(attempt__id=attempt_id).update(completed=timezone.now())

    # get exam session after submission
    res = client.get(f"/api/v1/exam/{exam.id}/session")
    assert res.status_code == 200, "get exam attempt after submission"
    assert res.json()["grade"]["completed"] is not None, "submit exam"

    # deactivate attempt
    res = client.delete(f"/api/v1/exam/{exam.id}/attempt/deactivate")
    assert res.status_code == (400 if exam.max_attempts <= 1 else 200), "deactivate attempt failed"

    # timestamp
    res = client.get("/api/v1/exam/timestamp")
    assert res.status_code == 200, "get timestamp"
