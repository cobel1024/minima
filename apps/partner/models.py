from typing import TYPE_CHECKING

import pghistory
from django.contrib.auth import get_user_model
from django.core import signing
from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    DateField,
    EmailField,
    ForeignKey,
    ImageField,
    ManyToManyField,
    QuerySet,
    TextField,
    UniqueConstraint,
    URLField,
)
from django.db.models.base import Model
from django.db.models.enums import TextChoices
from django.db.models.indexes import Index
from django.utils.translation import gettext_lazy as _
from pghistory.models import PghEventModel
from phonenumber_field.modelfields import PhoneNumberField

from apps.common.models import TimeStampedMixin

User = get_user_model()

if TYPE_CHECKING:
    from apps.account.models import User


@pghistory.track()
class Partner(TimeStampedMixin):
    name = CharField(_("Name"), max_length=50, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    phone = CharField(_("Phone"), max_length=20)  # char field
    email = EmailField(_("Email"))
    address = TextField(_("Address"), blank=True, default="")
    logo = ImageField(_("Logo"), null=True, blank=True)
    website = URLField(_("Website"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Partner")
        verbose_name_plural = _("Partners")
        indexes = [Index(fields=["email"])]

    if TYPE_CHECKING:
        businesssite_set: "QuerySet[BusinessSite]"

    def __str__(self):
        return self.name


@pghistory.track()
class BusinessSite(TimeStampedMixin):
    partner = ForeignKey(Partner, CASCADE, verbose_name=_("Partner"))
    name = CharField(_("Name"), max_length=50)
    description = TextField(_("Description"), blank=True, default="")
    business_number = CharField(_("Business Number"), max_length=50, unique=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Business Site")
        verbose_name_plural = _("Business Sites")
        constraints = [UniqueConstraint(fields=["partner", "name"], name="partner_business_pa_na_uniq")]

    if TYPE_CHECKING:
        employee_set: "QuerySet[Employee]"

    def __str__(self):
        return self.name


@pghistory.track()
class Employee(TimeStampedMixin):
    site = ForeignKey(BusinessSite, CASCADE, verbose_name=_("Business Site"))
    name = CharField(_("Name"), max_length=50)
    email = EmailField(_("Email"))
    birth_date = DateField(_("Birth Date"), null=True, blank=True)
    encrypted_id_number = CharField(_("ID Number"), blank=True, max_length=255)
    phone = PhoneNumberField(_("Phone"), blank=True, default="")
    team = CharField(_("Team"), blank=True, default="", max_length=50)
    job_position = CharField(_("Job Position"), blank=True, default="", max_length=50)
    job_title = CharField(_("Job Title"), blank=True, default="", max_length=50)
    employment_status = CharField(_("Employment Status"), blank=True, default="", max_length=50)
    employment_type = CharField(_("Employment Type"), blank=True, default="", max_length=50)
    user = ForeignKey(User, SET_NULL, null=True, blank=True, verbose_name=_("User"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Employee")
        verbose_name_plural = _("Employees")
        constraints = [UniqueConstraint(fields=["site", "email"], name="partner_employee_si_em_uniq")]
        indexes = [Index(fields=["name"]), Index(fields=["email"]), Index(fields=["phone"]), Index(fields=["team"])]

    if TYPE_CHECKING:
        pgh_event_model: PghEventModel

    ID_NUMBER_SALT = "id_number"

    @classmethod
    def encrypt_id_number(cls, id_number: str):
        if not id_number:
            return ""
        return signing.dumps(id_number, salt=cls.ID_NUMBER_SALT)

    @classmethod
    def decrypt_id_number(cls, encrypted_data: str):
        return signing.loads(encrypted_data, salt=cls.ID_NUMBER_SALT)

    def set_id_number(self, id_number: str):
        self.encrypted_id_number = self.encrypt_id_number(id_number) if id_number else ""

    def check_id_number(self, id_number: str):
        if not self.encrypted_id_number and not id_number:
            return True
        if not self.encrypted_id_number or not id_number:
            return False
        decrypted = self.decrypt_id_number(self.encrypted_id_number)
        return decrypted == id_number

    def __str__(self):
        return f"{self.name} {self.email}>"


@pghistory.track()
class Cohort(TimeStampedMixin):
    name = CharField(_("Name"), max_length=50, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    employees = ManyToManyField(Employee, verbose_name=_("Employees"))
    staffs = ManyToManyField(User, through="CohortStaff", blank=True, verbose_name=_("Staffs"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Cohort")
        verbose_name_plural = _("Cohorts")

    def __str__(self):
        return self.name


@pghistory.track()
class CohortEmployee(TimeStampedMixin):
    cohort = ForeignKey(Cohort, CASCADE, verbose_name=_("Cohort"))
    employee = ForeignKey(Employee, CASCADE, verbose_name=_("Employee"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Cohort Employee")
        verbose_name_plural = _("Cohort Employees")
        constraints = [UniqueConstraint(fields=["cohort", "employee"], name="partner_cohortemployee_co_em_uniq")]


@pghistory.track()
class CohortStaff(Model):
    class RoleChoices(TextChoices):
        EDUCATION_MANAGER = "education_manager", _("Education Manager")
        MARKETING_MANAGER = "marketing_manager", _("Marketing Manager")
        FINANCIAL_MANAGER = "financial_manager", _("Financial Manager")

    cohort = ForeignKey(Cohort, CASCADE, verbose_name=_("Cohort"))
    staff = ForeignKey(User, CASCADE, verbose_name=_("User"))
    role = CharField(_("Role"), max_length=30, choices=RoleChoices)

    class Meta:
        verbose_name = _("Cohort Staff")
        verbose_name_plural = _("Cohort Staffs")
        constraints = [UniqueConstraint(fields=["cohort", "staff"], name="partner_cohortstaff_co_sta_uniq")]
