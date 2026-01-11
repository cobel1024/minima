import logging
from datetime import timedelta
from typing import TYPE_CHECKING, TypedDict

import pghistory
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateTimeField,
    FileField,
    FloatField,
    ForeignKey,
    ImageField,
    Index,
    JSONField,
    ManyToManyField,
    Model,
    PositiveSmallIntegerField,
    TextField,
    UniqueConstraint,
)
from django.db.models.expressions import Exists
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from treebeard.mp_tree import MP_Node

from apps.common.error import ErrorCode
from apps.common.models import OrderableMixin, TimeStampedMixin, tuid
from apps.common.util import add_query_params
from apps.competency.certificate import (
    CertificateAwardDataDict,
    CertificateAwardFullDataDict,
    generate_certificate,
    validate_certificate_template,
)
from apps.partner.models import Partner

User = get_user_model()

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractUser as User


log = logging.getLogger(__name__)


class TreeNodeDict(TypedDict):
    id: int
    name: str  # name
    children: list["TreeNodeDict"]  # children


@pghistory.track()
class Classification(MP_Node):
    code = CharField(_("Code"), max_length=12, unique=True)
    name = CharField(_("Name"), max_length=200)
    version = CharField(_("Version"), max_length=30)
    ancestors = ArrayField(CharField(max_length=200), editable=False, verbose_name=_("Ancestors"))

    class Meta(MP_Node.Meta):
        verbose_name = _("Classification")
        verbose_name_plural = _("Classifications")
        indexes = [Index(fields=["name"]), Index(fields=["depth"]), Index(fields=["path"])]

    if TYPE_CHECKING:
        pk: int

    def __str__(self):
        return " / ".join(self.ancestors + [self.name])

    def save(self, *args, **kwargs):
        parent = self.get_parent()
        self.ancestors = parent.ancestors + [parent.name] if parent else []
        return super().save(*args, **kwargs)

    @classmethod
    async def get_tree_data(cls):
        nodes = [c async for c in cls.objects.filter(depth__lte=4).order_by("path")]
        tree: list[TreeNodeDict] = []
        stack: list = [{"children": tree}]
        for node in nodes:
            item: TreeNodeDict = {"id": node.id, "name": node.name, "children": []}
            while len(stack) > node.depth:
                stack.pop()
            stack[-1]["children"].append(item)
            stack.append(item)
        return tree

    @classmethod
    async def get_skills_data(cls, *, id: int):
        return [
            s async for s in Skill.objects.prefetch_related("factor_set").filter(classification_id=id).order_by("id")
        ]


@pghistory.track()
class Skill(Model):
    classification = ForeignKey(Classification, CASCADE, verbose_name=_("Classification"))
    code = CharField(_("Code"), max_length=12)
    name = CharField(_("Name"), max_length=200)
    level = PositiveSmallIntegerField(_("Level"))
    number = CharField(_("Number"), max_length=30, unique=True)
    version = CharField(_("Version"), max_length=30)

    class Meta:
        verbose_name = _("Skill")
        verbose_name_plural = _("Skills")
        indexes = [Index(fields=["classification", "level"]), Index(fields=["code"]), Index(fields=["name"])]

    if TYPE_CHECKING:
        classification_id: int

    def __str__(self):
        return f"{self.name} ({self.number})"


@pghistory.track()
class Factor(Model):
    skill = ForeignKey(Skill, CASCADE, verbose_name=_("Skill"))
    code = CharField(_("Code"), max_length=12)
    name = CharField(_("Name"), max_length=200)
    number = CharField(_("Number"), max_length=30, unique=True)
    version = CharField(_("Version"), max_length=30)

    class Meta:
        verbose_name = _("Factor")
        verbose_name_plural = _("Factors")
        indexes = [Index(fields=["code"]), Index(fields=["name"])]

    if TYPE_CHECKING:
        skill_id: int

    def __str__(self):
        return f"{self.name} ({self.number})"


@pghistory.track()
class CompetencyGoal(TimeStampedMixin, OrderableMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    name = CharField(_("Name"), max_length=200)
    description = TextField(_("Description"), default="", blank=True)
    classification = ForeignKey(Classification, CASCADE, verbose_name=_("Classification"))
    factors = ManyToManyField(Factor, verbose_name=_("Factors"))

    ordering_group = ("user",)

    class Meta:
        verbose_name = _("Competency Goal")
        verbose_name_plural = _("Competency Goals")
        constraints = [UniqueConstraint(fields=["user", "name"], name="competency_competencygoal_us_na_uniq")]

    if TYPE_CHECKING:
        factor_ids: list[int]

    @classmethod
    async def upsert(cls, *, user_id: str, factor_ids: list[int], name: str, **data: object):
        goal, created = await cls.objects.aupdate_or_create(user_id=user_id, name=name, defaults=data)
        await goal.factors.aset(factor_ids)
        goal.factor_ids = factor_ids
        return goal


@pghistory.track()
class Badge(TimeStampedMixin):
    name = CharField(_("Name"), max_length=50, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    image = ImageField(_("Image"))
    active = BooleanField(_("Active"), default=True)
    issuer = ForeignKey(Partner, CASCADE, verbose_name=_("Issuer"))
    validity_days = PositiveSmallIntegerField(_("Validity Days"), null=True, blank=True)
    skills = ManyToManyField(Skill, through="BadgeSkill", verbose_name=_("Skills"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Badge")
        verbose_name_plural = _("Badges")
        indexes = [Index(fields=["active"])]

    # TODO: badge image baking, JSON-LD API

    def __str__(self):
        return self.name


@pghistory.track()
class BadgeSkill(Model):
    badge = ForeignKey(Badge, CASCADE, verbose_name=_("Badge"))
    skill = ForeignKey(Skill, CASCADE, verbose_name=_("Skill"))
    factors = ManyToManyField(Factor, verbose_name=_("Factors"))
    coverage = FloatField(_("Coverage"))

    class Meta:
        verbose_name = _("Badge Skill")
        verbose_name_plural = _("Badge Skills")
        constraints = [UniqueConstraint(fields=["badge", "skill"], name="competency_badgeskill_ba_sk_uniq")]

    if TYPE_CHECKING:
        pk: int


@pghistory.track()
class BadgeEndorsement(Model):
    badge = ForeignKey(Badge, CASCADE, verbose_name=_("Badge"))
    partner = ForeignKey(Partner, CASCADE, verbose_name=_("Partner"))
    claim = TextField(_("Claim"))
    endorsed = DateTimeField(_("Endorsed"))

    class Meta:
        verbose_name = _("BadgeEndorsement")
        verbose_name_plural = _("Badge Endorsements")
        constraints = [UniqueConstraint(fields=["badge", "partner"], name="competency_badgeendorsement_ba_or_uniq")]


@pghistory.track()
class BadgeAward(TimeStampedMixin):
    badge = ForeignKey(Badge, CASCADE, verbose_name=_("Badge"))
    earner = ForeignKey(User, CASCADE, verbose_name=_("Earner"))
    expires = DateTimeField(_("Expires"), null=True, blank=True)
    revoked = DateTimeField(_("Revoked"), null=True, blank=True)
    revoked_reason = TextField(_("Revoked Reason"), blank=True, default="")

    # TODO badge evidence

    class Meta(TimeStampedMixin.Meta):
        constraints = [UniqueConstraint(fields=["badge", "earner"], name="competency_badgeaward_ba_ea_uniq")]
        verbose_name = _("Badge Award")
        verbose_name_plural = _("Badge Awards")


@pghistory.track()
class Certificate(TimeStampedMixin):
    name = CharField(_("Name"), max_length=50, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    background_image = ImageField(_("Background Image"))
    thumbnail = ImageField(_("Thumbnail"))
    template = JSONField(_("Template"))
    active = BooleanField(_("Active"), default=True)
    issuer = ForeignKey(Partner, CASCADE, verbose_name=_("Issuer"))
    validity_days = PositiveSmallIntegerField(_("Validity Days"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Certificate")
        verbose_name_plural = _("Certificates")
        indexes = [Index(fields=["active"])]

    if TYPE_CHECKING:
        awarded: bool  # annotated

    def __str__(self):
        return f"{self.name}"

    def clean(self):
        validate_certificate_template(self.template)


@pghistory.track()
class CertificateSkill(Model):
    certificate = ForeignKey(Certificate, CASCADE, verbose_name=_("Certificate"))
    skill = ForeignKey(Skill, CASCADE, verbose_name=_("Skill"))
    factors = ManyToManyField(Factor, verbose_name=_("Factors"))
    coverage = FloatField(_("Coverage"))

    class Meta:
        verbose_name = _("Certificate Skill")
        verbose_name_plural = _("Certificate Skills")
        constraints = [UniqueConstraint(fields=["certificate", "skill"], name="competency_certificateskill_co_sk_uniq")]

    if TYPE_CHECKING:
        pk: int


@pghistory.track()
class CertificateEndorsement(TimeStampedMixin):
    certificate = ForeignKey(Certificate, CASCADE, verbose_name=_("Certificate"))
    partner = ForeignKey(Partner, CASCADE, verbose_name=_("Partner"))
    claim = TextField(_("Claim"))
    endorsed = DateTimeField(_("Endorsed"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Certificate Endorsement")
        verbose_name_plural = _("Certificate Endorsements")
        constraints = [
            UniqueConstraint(fields=["certificate", "partner"], name="competency_certificateendorsement_ce_or_uniq")
        ]


@pghistory.track()
class CertificateAward(TimeStampedMixin):
    certificate = ForeignKey(Certificate, CASCADE, verbose_name=_("Certificate"))
    recipient = ForeignKey(User, CASCADE, verbose_name=_("Recipient"))
    pdf = FileField(_("PDF"))
    thumbnail = ImageField(_("Thumbnail"))
    data = JSONField(_("Data"))
    expires = DateTimeField(_("Expires"), null=True, blank=True)
    revoked = DateTimeField(_("Revoked"), null=True, blank=True)
    revoked_reason = TextField(_("Revoked Reason"), blank=True, default="")
    context = CharField(_("Context Key"), max_length=255, blank=True, default="")

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Certificate Award")
        verbose_name_plural = _("Certificate Awards")
        constraints = [
            UniqueConstraint(
                fields=["certificate", "recipient", "context"], name="competency_certificateaward_ce_re_co_ke_uniq"
            )
        ]

    @classmethod
    def generate_document_number(cls):
        return f"CERT-{timezone.now().year}-{tuid(10)[4:].upper()}"

    @classmethod
    async def issue(
        cls,
        *,
        certificate_id: int,
        recipient: User,
        context: str,
        data: CertificateAwardDataDict,
        verification_url: str,
    ):
        certificate = (
            await Certificate.objects
            .annotate(
                awarded=Exists(
                    CertificateAward.objects.filter(certificate_id=certificate_id, recipient=recipient, context=context)
                )
            )
            .select_related("issuer")
            .aget(id=certificate_id, active=True)
        )

        if certificate.awarded:
            raise ValueError(ErrorCode.CERTIFICATE_ALREADY_ISSUED)

        expires = timezone.now() + timedelta(days=certificate.validity_days) if certificate.validity_days else None

        full_data = CertificateAwardFullDataDict(
            document_number=cls.generate_document_number(),
            issuer_name=certificate.issuer.name,
            issue_date=timezone.now().strftime("%Y-%m-%d"),
            expiration_date=expires.strftime("%Y-%m-%d") if expires else "",
            document_title=data["document_title"],
            completion_title=data["completion_title"],
            completion_period=data["completion_period"],
            completion_hours=data["completion_hours"],
            recipient_name=data["recipient_name"],
            recipient_birth_date=data["recipient_birth_date"],
        )

        # reverse url for verification
        verification_url = add_query_params(verification_url, doc=full_data["document_number"])

        pdf_content, thumbnail_content = await generate_certificate(
            background_image=certificate.background_image.file,
            template=certificate.template,
            data=full_data,
            verification_url=verification_url,
        )

        return await CertificateAward.objects.acreate(
            certificate=certificate,
            recipient=recipient,
            pdf=pdf_content,
            thumbnail=thumbnail_content,
            data=full_data,
            expires=expires,
            context=context,
        )
