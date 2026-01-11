from itertools import cycle
from typing import TYPE_CHECKING

import mimesis
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from factory.declarations import LazyFunction, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.plugins.factory import FactoryField

from apps.account.models import User
from apps.common.util import tuid
from apps.partner.models import BusinessSite, Cohort, CohortEmployee, CohortStaff, Employee, Partner

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class PartnerFactory(DjangoModelFactory[Partner]):
    name = FactoryField("company")
    description = FactoryField("sentence")
    phone = FactoryField("phone_number")
    email = FactoryField("email")
    address = FactoryField("address")
    logo = LazyFunction(lambda: ContentFile(generic.binaryfile.image(file_type=mimesis.ImageFile.PNG), "logo.png"))
    website = FactoryField("url")

    class Meta:
        model = Partner
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        businesssite_set: QuerySet[BusinessSite]

    @post_generation
    def cohort_set(self, create: bool, extracted, **kwargs):
        if not create:
            return

        if self.businesssite_set.exists():
            return

        BusinessSiteFactory.reset_sequence()
        BusinessSiteFactory.create_batch(generic.random.randint(1, 10), partner=self)


class BusinessSiteFactory(DjangoModelFactory[BusinessSite]):
    partner = SubFactory(PartnerFactory)
    name = FactoryField("word")
    description = FactoryField("text")
    business_number = LazyFunction(lambda: tuid())

    class Meta:
        model = BusinessSite
        django_get_or_create = ("partner", "name")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        employee_set: QuerySet[Employee]

    @post_generation
    def post_generation(self, create: bool, extracted, **kwargs):
        if not create:
            return

        if self.employee_set.exists():
            return

        EmployeeFactory.create_batch(generic.random.randint(5, 10), site=self)


class EmployeeFactory(DjangoModelFactory[Employee]):
    site = SubFactory(BusinessSiteFactory)
    name = FactoryField("full_name")
    email = FactoryField("email")
    birth_date = FactoryField("date", start=1950, end=2000)
    encrypted_id_number = LazyFunction(
        lambda: Employee.encrypt_id_number(f"{generic.person.identifier()}-{generic.cryptographic.uuid()[:8]}")
    )
    phone = FactoryField("phone_number")
    team = FactoryField("fruit")
    job_position = FactoryField("color")
    job_title = FactoryField("occupation")
    employment_status = ""
    employment_type = ""

    class Meta:
        model = Employee
        django_get_or_create = ("site", "email")


class CohortFactory(DjangoModelFactory[Cohort]):
    name = FactoryField("color")
    description = FactoryField("text")

    class Meta:
        model = Cohort
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted, **kwargs):
        if not create:
            return

        employees = Employee.objects.order_by("?")[: generic.random.randint(20, 30)]
        CohortEmployee.objects.bulk_create(
            [CohortEmployee(cohort=self, employee=employee) for employee in employees], ignore_conflicts=True
        )

        users = User.objects.order_by("?")[: generic.random.randint(1, 3)]
        role_cycle = cycle([choice[0] for choice in CohortStaff.RoleChoices.choices])
        CohortStaff.objects.bulk_create(
            [CohortStaff(cohort=self, staff=user, role=next(role_cycle)) for user in users], ignore_conflicts=True
        )
