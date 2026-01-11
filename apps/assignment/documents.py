import re
from typing import TypedDict

from django.conf import settings
from django.db import models
from django_opensearch_dsl.documents import Document
from django_opensearch_dsl.fields import KeywordField, NestedField, TextField
from django_opensearch_dsl.registries import registry

from apps.assignment.models import Submission
from apps.common.search import AnswerAnalyzerMixin


class SimilarityCheckResponse(TypedDict):
    has_similar: bool
    similarity_percentage: int
    similar_answer: str | None
    similar_user_id: str | None


@registry.register_document
class SubmissionDocument(Document, AnswerAnalyzerMixin):
    class Index:
        name = "assignment_submission"
        settings = settings.OPENSEARCH_DSL_SETTINGS

    class Django:
        model = Submission

    answers = NestedField(
        properties={
            "question_id": KeywordField(),
            "answer": TextField(analyzer=settings.OPENSEARCH_TEXT_ANALYZER, fielddata=True),
        }
    )
    user_id = KeywordField()

    def should_index_object(self, object_instance: models.Model) -> bool:
        if isinstance(object_instance, Submission):
            return bool(object_instance.extracted_text)
        return False

    def prepare_answers(self, instance: Submission):
        return [{"question_id": str(instance.attempt.question_id), "answer": instance.extracted_text}]

    def prepare_user_id(self, instance: Submission):
        return instance.attempt.learner_id

    @classmethod
    def check_similarity(cls, *, question_id: int, user_id: str, text: str):
        search = cls.search().filter(
            "nested", path="answers", query={"term": {"answers.question_id": str(question_id)}}
        )
        search = search.exclude("term", user_id=user_id)
        search = search.query(
            "nested",
            path="answers",
            query={
                "more_like_this": {
                    "fields": ["answers.answer"],
                    "like": text,
                    "min_term_freq": 1,
                    "min_doc_freq": 1,
                    "minimum_should_match": "1%",
                    "max_query_terms": 1000,
                }
            },
        )
        search = search.extra(size=10)
        search = search.source(["answers", "user_id"])
        response = search.execute()

        result = SimilarityCheckResponse(
            has_similar=False, similarity_percentage=0, similar_answer=None, similar_user_id=None
        )

        if not response.hits:
            return result

        def normalize(t):
            return re.sub(r"\s+", "", t.strip())

        def char_ngrams(t, n=3):
            return set(t[i : i + n] for i in range(len(t) - n + 1))

        norm_text = normalize(text)
        text_ngrams = char_ngrams(norm_text)

        best_match = None
        best_ratio = 0

        for hit in response.hits:
            matching_answer = None
            for ans in hit.answers:
                if str(ans.question_id) == str(question_id):
                    matching_answer = ans.answer
                    break

            if not matching_answer:
                continue

            norm_answer = normalize(matching_answer)
            answer_ngrams = char_ngrams(norm_answer)

            if text_ngrams and answer_ngrams:
                intersection = len(text_ngrams & answer_ngrams)
                union = len(text_ngrams | answer_ngrams)
                ratio = int((intersection / union) * 100)

                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = (matching_answer, hit.user_id)

        if best_ratio >= 60 and best_match:
            result = SimilarityCheckResponse(
                has_similar=True,
                similarity_percentage=best_ratio,
                similar_answer=best_match[0],
                similar_user_id=best_match[1],
            )

        return result
