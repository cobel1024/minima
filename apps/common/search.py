from typing import TYPE_CHECKING, Sequence, cast

from django_opensearch_dsl.documents import Document


class AnswerAnalyzerMixin:
    @classmethod
    def analyze_answers(cls, question_ids: Sequence[int | str]):

        if TYPE_CHECKING:
            cls = cast(type[Document], cls)

        ids = [str(qid) for qid in question_ids]
        search = cls.search().filter("nested", path="answers", query={"terms": {"answers.question_id": ids}})
        search = search.extra(size=0)
        nested_agg = search.aggs.bucket("all_answers", "nested", path="answers")
        filtered_agg = nested_agg.bucket("filtered_answers", "filter", {"terms": {"answers.question_id": ids}})
        terms = filtered_agg.bucket("by_question", "terms", field="answers.question_id", size=len(question_ids))
        terms.bucket("answer_stats", "terms", field="answers.answer", size=12, min_doc_count=1)
        response = search.execute()
        stats: dict[str, dict[str, int]] = {}
        if hasattr(response.aggregations, "all_answers") and hasattr(
            response.aggregations.all_answers, "filtered_answers"
        ):
            for question_bucket in response.aggregations.all_answers.filtered_answers.by_question.buckets:
                question_id = str(question_bucket.key)
                answer_frequencies: dict[str, int] = {}
                for answer_bucket in question_bucket.answer_stats.buckets:
                    answer_frequencies[str(answer_bucket.key)] = int(answer_bucket.doc_count)
                stats[question_id] = answer_frequencies
        for question_id in question_ids:
            if str(question_id) not in stats:
                stats[str(question_id)] = {}
        return stats
