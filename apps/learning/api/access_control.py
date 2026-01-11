import logging
from functools import wraps

from celery.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.common.error import ErrorCode
from apps.common.util import AccessDate, HttpRequest, openapi_query_param
from apps.content.models import PublicAccessMedia
from apps.course.models import Course
from apps.learning.models import Enrollment

log = logging.getLogger(__name__)


def access_date(app_label, model, *, id_field: str = "id"):
    def decorator(func):
        openapi_query_param(func=func, name="course", schema_type="string", required=False, nullable=False)

        @wraps(func)
        async def wrapper(request: HttpRequest, *args, **kwargs):
            user_id = request.auth
            content_id = kwargs.get(id_field)

            if not content_id:
                raise ImproperlyConfigured("id_field is required")

            course_id = request.GET.get("course")

            # step 1: check enrollment

            if course_id:
                candidate = (course_id, Course._meta.app_label, Course._meta.model.__name__.lower())
            else:
                candidate = (content_id, app_label, model)

            enrollment = await Enrollment.objects.filter(
                user_id=user_id,
                active=True,
                content_id=candidate[0],
                content_type__app_label=candidate[1],
                content_type__model=candidate[2],
            ).afirst()  # unique

            public_access = None
            if app_label == "content" and model == "media":
                public_access = await PublicAccessMedia.get_access_date(media_id=content_id)

            # more favorable access date between enrollment and public access
            accessible = _get_favorable_date(enrollment, public_access)

            # step 2: override accessible date by context

            if course_id:
                try:
                    accessible = await Course.content_effective_date(
                        course_id=course_id,
                        content_id=content_id,
                        app_label=app_label,
                        model=model,
                        access_date=accessible,
                    )
                except ValueError as e:
                    log.error(e, exc_info=True)
                    raise ValueError(ErrorCode.ACCESS_DENIED)

            # step 3: check access date

            now = timezone.now()

            if now < accessible["start"]:
                raise ValueError(ErrorCode.CONTENT_NOT_AVAILABLE)

            if now >= accessible["archive"]:
                raise ValueError(ErrorCode.REVIEW_PERIOD_OVER)

            if accessible["end"] <= now < accessible["archive"]:
                if request.method not in ["GET", "HEAD", "OPTIONS"]:
                    raise ValueError(ErrorCode.CONTENT_READ_ONLY)

            # pass access date
            setattr(request, "access_date", accessible)
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator


def _get_favorable_date(a: Enrollment | None, b: PublicAccessMedia | None) -> AccessDate:
    if a and b:
        return AccessDate(start=min(a.start, b.start), end=max(a.end, b.end), archive=max(a.archive, b.archive))
    c = a or b
    if c:
        return AccessDate(start=c.start, end=c.end, archive=c.archive)
    raise ValueError(ErrorCode.ACCESS_DENIED)


def active_context():
    def decorator(func):
        openapi_query_param(func=func, name="course", schema_type="string", required=False, nullable=False)

        @wraps(func)
        async def wrapper(request: HttpRequest, *args, **kwargs):
            user_id = request.auth
            course_id = request.GET.get("course")

            # With active unique pattern, active context is unique but multiple contexts can exist.
            # Frontend only accesses active context, so no need to distinguish between context and active context
            # When frontend sends current context, server must fetch and save active context value for snapshot
            # Here we convert current context to active context

            active_context = ""  # default: standalone
            if course_id:
                active_context = await Course.issue_context(course_id=course_id, user_id=user_id)

            request.active_context = active_context
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
