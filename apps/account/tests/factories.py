import re

import mimesis
from django.conf import settings
from django.contrib.auth.hashers import make_password
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute
from mimesis.plugins.factory import FactoryField
from phonenumbers import country_code_for_region

from apps.account.models import User

person = mimesis.Person(settings.DEFAULT_LANGUAGE)
generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


hashed_password = make_password("1111")


class UserFactory(DjangoModelFactory[User]):
    email = FactoryField("email")
    name = FactoryField("full_name")
    nickname = FactoryField("word")
    birth_date = FactoryField("date", start=1950, end=2000)
    language = FactoryField("choice", items=["en", "ko", ""])

    password = hashed_password
    is_active = True
    preferences = FactoryField("choice", items=[{"theme": "light"}, {"theme": "dark"}])

    @lazy_attribute
    def phone(self):
        region = settings.PHONENUMBER_DEFAULT_REGION
        country_code = country_code_for_region(region)
        raw_number = re.sub(r"[^\d]", "", person.phone_number())
        return f"+{country_code}{raw_number[-10:]}"

    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = True
