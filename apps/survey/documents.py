from django.conf import settings
from django_opensearch_dsl.documents import Document
from django_opensearch_dsl.fields import KeywordField, NestedField, TextField
from django_opensearch_dsl.registries import registry

from apps.survey.models import Submission


@registry.register_document
class SubmissionDocument(Document):
    class Index:
        name = "survey_submission"
        settings = settings.OPENSEARCH_DSL_SETTINGS

    class Django:
        model = Submission

    answers = NestedField(
        properties={
            "question_id": KeywordField(),
            "answer": TextField(analyzer=settings.OPENSEARCH_TEXT_ANALYZER, fielddata=True),
        }
    )

    def prepare_answers(self, instance: Submission):
        return [{"question_id": str(question_id), "answer": answer} for question_id, answer in instance.answers.items()]
