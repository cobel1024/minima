import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.assignment.documents import SubmissionDocument
from apps.assignment.models import PlagiarismCheck, Submission
from apps.assignment.tests.factories import AssignmentFactory, RubricFactory


@pytest.mark.django_db
def test_assignment():
    AssignmentFactory.create()
    RubricFactory.create()


@pytest.mark.load_data
def test_load_assignment_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        assignments = AssignmentFactory.create_batch(10)

        # plagiarism data
        submissions = Submission.objects.select_related("attempt", "attempt__question").filter(
            attempt__assignment_id__in=[assignment.pk for assignment in assignments]
        )

        plagiarism_checks = []
        for submission in submissions:
            check_result = SubmissionDocument.check_similarity(
                question_id=submissions[0].attempt.question_id,
                user_id=submission.attempt.learner_id,
                text=submission.extracted_text,
            )

            if not check_result["has_similar"]:
                continue

            plagiarism_checks.append(
                PlagiarismCheck(
                    attempt_id=submission.attempt.pk,
                    status=PlagiarismCheck.StatusChoices.DETECTED
                    if check_result["similarity_percentage"] >= submission.attempt.question.plagiarism_threshold
                    else PlagiarismCheck.StatusChoices.NOT_DETECTED,
                    similarity_percentage=check_result["similarity_percentage"],
                    flagged_text=submission.extracted_text.strip(),
                    source_text=(check_result["similar_answer"] or "").strip(),
                    source_user_id=check_result["similar_user_id"],
                )
            )

        PlagiarismCheck.objects.bulk_create(plagiarism_checks, ignore_conflicts=True)
