from typing import TYPE_CHECKING

import mimesis
from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.translation import gettext as _
from factory.declarations import Iterator, LazyAttribute, LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.plugins.factory import FactoryField

from apps.account.tests.factories import UserFactory
from apps.competency.certificate import CertificateAwardDataDict, default_certificate_template
from apps.competency.models import (
    Badge,
    BadgeAward,
    BadgeEndorsement,
    BadgeSkill,
    Certificate,
    CertificateAward,
    CertificateEndorsement,
    CertificateSkill,
    Classification,
    CompetencyGoal,
    Factor,
    Skill,
)

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class BadgeFactory(DjangoModelFactory[Badge]):
    name = LazyFunction(lambda: " ".join(generic.text.words(generic.random.randint(3, 5))))
    description = FactoryField("sentence")
    image = LazyAttribute(
        lambda o: ContentFile(generic.binaryfile.image(file_type=mimesis.ImageFile.PNG), f"{o.name}.png")
    )
    active = True
    issuer = SubFactory("partner.tests.factories.PartnerFactory")

    class Meta:
        model = Badge
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        BadgeSkillFactory.create_batch(generic.random.randint(1, 3), badge=self)
        BadgeEndorsementFactory.create_batch(generic.random.randint(1, 2), badge=self)
        BadgeAwardFactory.create_batch(generic.random.randint(10, 20), badge=self)


class BadgeSkillFactory(DjangoModelFactory[BadgeSkill]):
    badge = SubFactory(BadgeFactory)
    skill = Iterator(Skill.objects.all())
    coverage = 0.0

    class Meta:
        model = BadgeSkill
        django_get_or_create = ("badge", "skill")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        factors = Factor.objects.filter(skill=self.skill)
        badge_factors = factors[: generic.random.randint(1, len(factors))]
        self.coverage = len(badge_factors) / len(factors) * 100
        self.save()

        self.factors.set(badge_factors)


class BadgeEndorsementFactory(DjangoModelFactory[BadgeEndorsement]):
    badge = SubFactory(BadgeFactory)
    partner = SubFactory("partner.tests.factories.PartnerFactory")
    claim = FactoryField("sentence")
    endorsed = LazyFunction(lambda: timezone.now())

    class Meta:
        model = BadgeEndorsement
        django_get_or_create = ("badge", "partner")


class BadgeAwardFactory(DjangoModelFactory[BadgeAward]):
    badge = SubFactory(BadgeFactory)
    earner = SubFactory(UserFactory)

    class Meta:
        model = BadgeAward
        django_get_or_create = ("badge", "earner")


class CertificateFactory(DjangoModelFactory[Certificate]):
    name = LazyFunction(lambda: " ".join(generic.text.words(generic.random.randint(3, 5))))
    description = FactoryField("sentence")
    background_image = LazyAttribute(
        lambda o: ContentFile(generic.binaryfile.image(file_type=mimesis.ImageFile.PNG), f"{o.name}.png")
    )
    thumbnail = LazyAttribute(
        lambda o: ContentFile(generic.binaryfile.image(file_type=mimesis.ImageFile.PNG), f"{o.name}.thumbnail.png")
    )
    template = LazyFunction(lambda: default_certificate_template())
    active = True
    issuer = SubFactory("partner.tests.factories.PartnerFactory")

    class Meta:
        model = Certificate
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        pk: int

    @post_generation
    def post_generation(self, create: bool, extracted: dict, **kwargs: object):
        if not create:
            return

        CertificateSkillFactory.create_batch(generic.random.randint(1, 3), certificate=self)
        CertificateEndorsementFactory.create_batch(generic.random.randint(1, 2), certificate=self)

        user = extracted["user"] if extracted and extracted["user"] else UserFactory()
        if not CertificateAward.objects.filter(certificate_id=self.pk, recipient=user, context="").exists():
            async_to_sync(CertificateAward.issue)(
                certificate_id=self.pk,
                recipient=user,
                context="",
                data=CertificateAwardDataDict(
                    document_title=_("Certificate of Completion"),
                    completion_title=" ".join(generic.text.words(generic.random.randint(5, 8))),
                    completion_period="2000-01-01 ~ 2050-01-01",
                    completion_hours=_("%(hours)s hours") % {"hours": str(generic.random.choice([4, 8, 16, 32, 64]))},
                    recipient_name=generic.person.full_name(),
                    recipient_birth_date=generic.person.birthdate().strftime("%Y-%m-%d"),
                ),
                verification_url="https://example.com/verify",
            )


class CertificateSkillFactory(DjangoModelFactory[CertificateSkill]):
    certificate = SubFactory(CertificateFactory)
    skill = Iterator(Skill.objects.all())
    coverage = 0.0

    class Meta:
        model = CertificateSkill
        django_get_or_create = ("certificate", "skill")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        factors = Factor.objects.filter(skill=self.skill)
        certificate_factors = factors[: generic.random.randint(1, len(factors))]
        self.coverage = len(certificate_factors) / len(factors) * 100
        self.save()

        self.factors.set(certificate_factors)


class CertificateEndorsementFactory(DjangoModelFactory[CertificateEndorsement]):
    certificate = SubFactory(CertificateFactory)
    partner = SubFactory("partner.tests.factories.PartnerFactory")
    claim = FactoryField("sentence")
    endorsed = LazyFunction(lambda: timezone.now())

    class Meta:
        model = CertificateEndorsement
        django_get_or_create = ("certificate", "partner")


class CompetencyGoalFactory(DjangoModelFactory[CompetencyGoal]):
    user = SubFactory(UserFactory)
    name = LazyFunction(lambda: " ".join(generic.text.words(generic.random.randint(3, 5))))
    description = FactoryField("sentence")
    classification = Iterator(Classification.objects.filter(depth=4)[:10])

    class Meta:
        model = CompetencyGoal
        django_get_or_create = ("user", "name")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        self.factors.set(Factor.objects.filter(skill__classification=self.classification))
