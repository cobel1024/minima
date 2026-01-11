from django.contrib.postgres.aggregates import ArrayAgg
from django.db.models import Prefetch, Q
from ninja import Query, Router

from apps.common.error import ErrorCode
from apps.common.util import HttpRequest
from apps.competency.api.schema import (
    CertificateFilterSchema,
    CertificateSchema,
    ClassificationTreeNodeSchema,
    CompetencyGoalSaveSchema,
    CompetencyGoalSchema,
    SkillDataSchema,
)
from apps.competency.models import Certificate, CertificateEndorsement, CertificateSkill, Classification, CompetencyGoal

router = Router(by_alias=True)


@router.get("/certificate", response=list[CertificateSchema])
async def get_certificates(request: HttpRequest, filter: Query[CertificateFilterSchema]):
    qs = (
        Certificate.objects
        .select_related("issuer")
        .prefetch_related(
            Prefetch(
                "certificateskill_set",
                CertificateSkill.objects.select_related("skill__classification").prefetch_related("factors"),
            ),
            Prefetch("certificateendorsement_set", CertificateEndorsement.objects.select_related("partner")),
        )
        .filter(active=True)
    )
    return [c async for c in filter.filter(qs)]


@router.get("/goal", response=list[CompetencyGoalSchema])
async def get_competency_goals(request: HttpRequest):
    return [
        c
        async for c in CompetencyGoal.objects
        .filter(user_id=request.auth)
        .annotate(factor_ids=ArrayAgg("factors__id", distinct=True, filter=Q(factors__id__isnull=False), default=[]))
        .order_by("ordering")
    ]


@router.post("/goal", response=CompetencyGoalSchema)
async def save_competency_goal(request: HttpRequest, data: CompetencyGoalSaveSchema):
    return await CompetencyGoal.upsert(user_id=request.auth, **data.model_dump())


@router.delete("/goal/{id}")
async def delete_competency_goal(request: HttpRequest, id: int):
    deleteed, _ = await CompetencyGoal.objects.filter(pk=id, user_id=request.auth).adelete()
    if not deleteed:
        raise ValueError(ErrorCode.NOT_FOUND)


@router.get("/classification/tree", response=list[ClassificationTreeNodeSchema])
async def get_classification_tree(request: HttpRequest):
    return await Classification.get_tree_data()


@router.get("/classification/{id}/skill/data", response=list[SkillDataSchema])
async def get_classification_skills_data(request: HttpRequest, id: int):
    return await Classification.get_skills_data(id=id)
