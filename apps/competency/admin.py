from django.contrib import admin
from django.http import HttpRequest

from apps.common.admin import (
    HiddenModelAdmin,
    ModelAdmin,
    ReadOnlyHiddenModelAdmin,
    ReadOnlyModelAdmin,
    ReadOnlyTabularInline,
    TabularInline,
)
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


@admin.register(Classification)
class ClassificationAdmin(ReadOnlyModelAdmin[Classification]):
    class CompetencySkillInline(ReadOnlyTabularInline[Skill]):
        model = Skill

    inlines = (CompetencySkillInline,)

    def get_list_display(self, request: HttpRequest):
        return ("__str__", "code", "version")


@admin.register(Factor)
class FactorAdmin(ReadOnlyHiddenModelAdmin[Factor]):
    def get_list_display(self, request: HttpRequest):
        return ("name", "code", "number", "version")


@admin.register(CompetencyGoal)
class CompetencyGoalAdmin(ModelAdmin[CompetencyGoal]):
    pass


@admin.register(Badge)
class BadgeAdmin(ModelAdmin[Badge]):
    class BadgeEndorsementInline(TabularInline[BadgeEndorsement]):
        model = BadgeEndorsement

    class BadgeSkillInline(ReadOnlyTabularInline[BadgeSkill]):
        model = BadgeSkill

    inlines = (BadgeSkillInline, BadgeEndorsementInline)


@admin.register(Skill)
class CompetencySkillAdmin(ReadOnlyHiddenModelAdmin[Skill]):
    class SkillFactorInline(TabularInline[Factor]):
        model = Factor

    inlines = (SkillFactorInline,)

    def get_list_display(self, request: HttpRequest):
        return ("name", "code", "number", "version")


@admin.register(BadgeAward)
class BadgeAwardedAdmin(ModelAdmin[BadgeAward]):
    pass


@admin.register(Certificate)
class CertificateAdmin(ModelAdmin[Certificate]):
    class CertificateEndorsementInline(TabularInline[CertificateEndorsement]):
        model = CertificateEndorsement

    class CertificateSkillInline(TabularInline[CertificateSkill]):
        model = CertificateSkill

    inlines = (CertificateSkillInline, CertificateEndorsementInline)


@admin.register(CertificateAward)
class CertificateAwardAdmin(ModelAdmin[CertificateAward]):
    def get_search_fields(self, request: HttpRequest):
        return [*self.search_fields, "data__document_number"]


@admin.register(BadgeSkill)
class BadgeSkillAdmin(HiddenModelAdmin[BadgeSkill]):
    pass


@admin.register(BadgeEndorsement)
class BadgeEndorsementAdmin(HiddenModelAdmin[BadgeEndorsement]):
    pass


@admin.register(CertificateSkill)
class CertificateSkillAdmin(HiddenModelAdmin[CertificateSkill]):
    pass


@admin.register(CertificateEndorsement)
class CertificateEndorsementAdmin(HiddenModelAdmin[CertificateEndorsement]):
    pass
