from django.urls import reverse
from ninja.router import Router

from apps.common.util import HttpRequest
from apps.course.api.schema import (
    CourseCertificateRequestSchema,
    CourseDetailSchema,
    CourseEngagementSchema,
    CourseSessionSchema,
)
from apps.course.models import Course, Engagement
from apps.learning.api.access_control import access_date

router = Router(by_alias=True)


@router.get("/{id}/session", response=CourseSessionSchema)
@access_date("course", "course")
async def get_session(request: HttpRequest, id: str):
    return await Course.get_session(course_id=id, learner_id=request.auth, access_date=request.access_date)


@router.post("/{id}/engage", response=CourseEngagementSchema)
@access_date("course", "course")
async def start_engagement(request: HttpRequest, id: str):
    return await Engagement.start(course_id=id, learner_id=request.auth)


@router.get("/{id}/detail", response=CourseDetailSchema)
async def get_detail(request: HttpRequest, id: str):
    return await Course.get_detail(id)


@router.post("/{id}/certificate/request")
async def request_certificate(request: HttpRequest, id: str, data: CourseCertificateRequestSchema):
    # cf competency/views.py
    verification_url = request.build_absolute_uri(reverse("verify_certificate"))
    return await Engagement.request_certificate(
        course_id=id, user_id=request.auth, certificate_id=data.certificate_id, verification_url=verification_url
    )
