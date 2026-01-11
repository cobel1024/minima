from django.http.request import HttpRequest
from django.shortcuts import render
from django.utils import timezone

from apps.competency.models import CertificateAward


def verify_certificate(request: HttpRequest):
    # Do not change 'doc' name. It is used in issuing cerfiticate.
    doc = request.GET.get("doc")

    if not doc:
        context = {"error": 400}

    else:
        context = {
            "award": (
                CertificateAward.objects
                .select_related("recipient", "certificate__issuer")
                .filter(data__document_number=doc)
                .first()
            ),
            "now": timezone.now(),
        }

    return render(request, "competency/certificate_verification.html", context)
