from typing import TYPE_CHECKING, TypedDict

import mimesis
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from factory.declarations import Iterator, LazyAttribute, LazyFunction, Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import lazy_attribute, post_generation
from mimesis.plugins.factory import FactoryField

from apps.account.tests.factories import UserFactory
from apps.operation.models import (
    FAQ,
    Announcement,
    Attachment,
    Category,
    Comment,
    FAQItem,
    HonorCode,
    Inquiry,
    InquiryResponse,
    Instructor,
    Message,
    Policy,
    PolicyVersion,
    Thread,
)

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class AnnouncementFactory(DjangoModelFactory[Announcement]):
    title = FactoryField("sentence")
    body = LazyFunction(
        lambda: "\n\n".join([
            generic.text.text(quantity=generic.random.randint(5, 8)) for _ in range(generic.random.randint(3, 5))
        ])
    )
    public = True
    pinned = LazyFunction(lambda: generic.random.weighted_choice({True: 1, False: 9}))

    class Meta:
        model = Announcement
        django_get_or_create = ("title",)


class InstructorFactory(DjangoModelFactory[Instructor]):
    name = FactoryField("full_name", reverse=True)
    email = FactoryField("email")
    about = FactoryField("text", quantity=generic.random.randint(5, 8))
    bio = LazyFunction(lambda: [generic.text.title()[:30] for _ in range(generic.random.randint(5, 8))])
    avatar = LazyFunction(lambda: ContentFile(generic.binaryfile.image(file_type=mimesis.ImageFile.PNG), "avatar.png"))
    active = True

    class Meta:
        model = Instructor
        django_get_or_create = ("email",)


class HonorCodeFactory(DjangoModelFactory[HonorCode]):
    title = LazyFunction(lambda: f"{generic.food.fruit()} {_('Honor Code')}")
    code = LazyFunction(
        lambda: "\n\n".join([
            generic.text.text(quantity=generic.random.randint(2, 4)) for _ in range(generic.random.randint(5, 10))
        ])
    )

    class Meta:
        model = HonorCode
        django_get_or_create = ("title",)


class FAQFactory(DjangoModelFactory[FAQ]):
    name = FactoryField("text.title")
    description = FactoryField("sentence")

    class Meta:
        model = FAQ
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        for __ in range(generic.random.randint(5, 7)):
            FAQItemFactory(faq=self)


class FAQItemFactory(DjangoModelFactory[FAQItem]):
    question = FactoryField("sentence")
    answer = FactoryField("text", quantity=generic.random.randint(3, 5))
    active = True

    class Meta:
        model = FAQItem
        django_get_or_create = ("faq", "question")


class AttachmentFactory(DjangoModelFactory[Attachment]):
    file = LazyFunction(
        lambda: ContentFile(
            generic.binaryfile.document(file_type=mimesis.DocumentFile.PDF), f"{generic.random.randint(1000, 9999)}.pdf"
        )
    )
    size = LazyAttribute(lambda o: o.file.size)
    mime_type = "application/pdf"

    class Meta:
        model = Attachment
        django_get_or_create = ("file",)
        skip_postgeneration_save = True


class InquiryFactory(DjangoModelFactory[Inquiry]):
    title = FactoryField("text.title")
    question = FactoryField("text")
    writer = SubFactory(UserFactory)
    content_id = None

    class Meta:
        model = Inquiry
        django_get_or_create = ("content_id", "title")
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        inquiryresponse_set: "QuerySet[InquiryResponse]"

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        if self.inquiryresponse_set.exists():
            return

        for i in range(generic.random.randint(0, 3)):
            InquiryResponseFactory.create(inquiry=self, solved=timezone.now() if (i == 2) else False)


class InquiryResponseFactory(DjangoModelFactory[InquiryResponse]):
    answer = FactoryField("text")
    writer = SubFactory(UserFactory)
    solved = None

    class Meta:
        model = InquiryResponse


class MessageFactory(DjangoModelFactory[Message]):
    channel = Iterator(Message.ChannelChoices)
    title = LazyFunction(lambda: generic.text.title())
    body = LazyFunction(lambda: generic.text.text())
    recipients = LazyFunction(lambda: [generic.person.email()])
    user = SubFactory("account.tests.factories.UserFactory")

    class Meta:
        model = Message


class PolicyFactory(DjangoModelFactory[Policy]):
    kind = Iterator(Policy.KindChoices)
    title = Iterator([choice[1] for choice in Policy.KindChoices.choices])
    description = FactoryField("text")
    active = True
    mandatory = True
    show_on_join = True

    class Meta:
        model = Policy
        django_get_or_create = ("kind",)
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        PolicyVersionFactory.reset_sequence()
        PolicyVersionFactory.create_batch(generic.random.randint(1, 3), policy=self)


class PolicyVersionFactory(DjangoModelFactory[PolicyVersion]):
    body = LazyFunction(
        lambda: "\n\n".join([
            generic.text.text(quantity=generic.random.randint(1, 3)) for _ in range(generic.random.randint(10, 20))
        ])
    )
    version = Sequence(lambda n: f"{n + 1}.0.0")
    effective_date = LazyFunction(lambda: timezone.now())

    class Meta:
        model = PolicyVersion
        django_get_or_create = ("policy", "version")

    @lazy_attribute
    def data_category(self):
        return {"privacy": generic.text.words(quantity=generic.random.randint(3, 5))}


generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)


class ThreadFactory(DjangoModelFactory[Thread]):
    title = FactoryField("text.title")
    description = FactoryField("text", quantity=generic.random.randint(1, 3))

    class Meta:
        model = Thread
        django_get_or_create = ("subject_type", "subject_id")
        skip_postgeneration_save = True

    @post_generation
    def post_generation(self, create: bool, extracted: object, **kwargs: object):
        if not create:
            return

        comments = CommentFactory.create_batch(generic.random.randint(5, 20), thread=self)
        for comment in comments:
            if generic.random.randint(1, 5) == 1:
                CommentFactory.create_batch(generic.random.randint(1, 5), thread=self, parent=comment)


class CommentFactory(DjangoModelFactory[Comment]):
    comment = FactoryField("text", quantity=generic.random.randint(2, 10))
    pinned = LazyFunction(lambda: generic.random.weighted_choice({True: 1, False: 9}))
    deleted = LazyFunction(lambda: generic.random.weighted_choice({True: 1, False: 9}))
    rating = LazyFunction(lambda: generic.random.randint(1, 5))
    writer = SubFactory("account.tests.factories.UserFactory")

    class Meta:
        model = Comment


def isced_sample_category():
    with transaction.atomic():
        roots: dict[str, Category] = {}

        for level_1_code, level_1_info in ISCED_STRUCTURE.items():
            existing_roots = Category.get_root_nodes().filter(name=level_1_info["name"])

            root = existing_roots.first()
            if not root:
                root = Category.add_root(name=level_1_info["name"])

            roots[level_1_code] = root

        for level_1_code, root in roots.items():
            level_1_info = ISCED_STRUCTURE[level_1_code]
            level_2_nodes = {}

            for level_2_code, level_2_info in level_1_info["level_2_fields"].items():
                existing_level_2 = root.get_children().filter(name=level_2_info["name"])

                level_2_node = existing_level_2.first()
                if not level_2_node:
                    level_2_node = root.add_child(name=level_2_info["name"])

                level_2_nodes[level_2_code] = level_2_node

                for __, level_3_name in level_2_info["level_3_fields"].items():
                    existing_level_3 = level_2_node.get_children().filter(name=level_3_name)

                    if not existing_level_3.exists():
                        level_2_node.add_child(name=level_3_name)

        return roots


"""
ISCED-F 2013 Categories
"""


class Level2Field(TypedDict):
    name: str
    level_3_fields: dict[str, str]


class Level1Field(TypedDict):
    name: str
    level_2_fields: dict[str, Level2Field]


ISCED_STRUCTURE = {
    "00": {
        "name": _("Generic programmes and qualifications"),
        "level_2_fields": {
            "001": {
                "name": _("Basic programmes and qualifications"),
                "level_3_fields": {"0011": _("Basic programmes and qualifications")},
            },
            "002": {"name": _("Literacy and numeracy"), "level_3_fields": {"0021": _("Literacy and numeracy")}},
            "003": {
                "name": _("Personal skills and development"),
                "level_3_fields": {"0031": _("Personal skills and development")},
            },
        },
    },
    "01": {
        "name": _("Education"),
        "level_2_fields": {
            "011": {
                "name": _("Education & Studies"),
                "level_3_fields": {
                    "0111": _("Education science"),
                    "0112": _("Training for pre-school teachers"),
                    "0113": _("Teacher training without subject specialization"),
                    "0114": _("Teacher training with subject specialization"),
                },
            }
        },
    },
    "02": {
        "name": _("Arts and humanities"),
        "level_2_fields": {
            "021": {
                "name": _("Arts"),
                "level_3_fields": {
                    "0211": _("Audio-visual techniques and media production"),
                    "0212": _("Fashion, interior and industrial design"),
                    "0213": _("Fine arts"),
                    "0214": _("Handicrafts"),
                    "0215": _("Music and performing arts"),
                },
            },
            "022": {
                "name": _("Humanities (except languages)"),
                "level_3_fields": {
                    "0221": _("Religion and theology"),
                    "0222": _("History and archaeology"),
                    "0223": _("Philosophy and ethics"),
                },
            },
            "023": {
                "name": _("Languages"),
                "level_3_fields": {"0231": _("Language acquisition"), "0232": _("Literature and linguistics")},
            },
        },
    },
    "03": {
        "name": _("Social sciences, journalism and information"),
        "level_2_fields": {
            "031": {
                "name": _("Social and behavioural sciences"),
                "level_3_fields": {
                    "0311": _("Economics"),
                    "0312": _("Political sciences and civics"),
                    "0313": _("Psychology"),
                    "0314": _("Sociology and cultural studies"),
                },
            },
            "032": {
                "name": _("Journalism and information"),
                "level_3_fields": {
                    "0321": _("Journalism and reporting"),
                    "0322": _("Library, information and archival studies"),
                },
            },
        },
    },
    "04": {
        "name": _("Business, administration and law"),
        "level_2_fields": {
            "041": {
                "name": _("Business and administration"),
                "level_3_fields": {
                    "0411": _("Accounting and taxation"),
                    "0412": _("Finance, banking and insurance"),
                    "0413": _("Management and administration"),
                    "0414": _("Marketing and advertising"),
                    "0415": _("Secretarial and office work"),
                    "0416": _("Wholesale and retail sales"),
                    "0417": _("Work skills"),
                },
            },
            "042": {"name": _("Law"), "level_3_fields": {"0421": _("Law")}},
        },
    },
    "05": {
        "name": _("Natural sciences, mathematics and statistics"),
        "level_2_fields": {
            "051": {
                "name": _("Biological and related sciences"),
                "level_3_fields": {"0511": _("Biology"), "0512": _("Biochemistry")},
            },
            "052": {
                "name": _("Environment"),
                "level_3_fields": {"0521": _("Environmental sciences"), "0522": _("Natural environments and wildlife")},
            },
            "053": {
                "name": _("Physical sciences"),
                "level_3_fields": {"0531": _("Chemistry"), "0532": _("Earth sciences"), "0533": _("Physics")},
            },
            "054": {
                "name": _("Mathematics and statistics"),
                "level_3_fields": {"0541": _("Mathematics"), "0542": _("Statistics")},
            },
        },
    },
    "06": {
        "name": _("Information"),
        "level_2_fields": {
            "061": {
                "name": _("Information and Communication Technologies"),
                "level_3_fields": {
                    "0611": _("Computer use"),
                    "0612": _("Database and network design and administration"),
                    "0613": _("Software and applications development and analysis"),
                },
            }
        },
    },
    "07": {
        "name": _("Engineering, manufacturing and construction"),
        "level_2_fields": {
            "071": {
                "name": _("Engineering and engineering trades"),
                "level_3_fields": {
                    "0711": _("Chemical engineering and processes"),
                    "0712": _("Environmental protection technology"),
                    "0713": _("Electricity and energy"),
                    "0714": _("Electronics and automation"),
                    "0715": _("Mechanics and metal trades"),
                    "0716": _("Motor vehicles, ships and aircraft"),
                },
            },
            "072": {
                "name": _("Manufacturing and processing"),
                "level_3_fields": {
                    "0721": _("Food processing"),
                    "0722": _("Materials (glass, paper, plastic and wood)"),
                    "0723": _("Textiles (clothes, footwear and leather)"),
                    "0724": _("Mining and extraction"),
                },
            },
            "073": {
                "name": _("Architecture and construction"),
                "level_3_fields": {
                    "0731": _("Architecture and town planning"),
                    "0732": _("Building and civil engineering"),
                },
            },
        },
    },
    "08": {
        "name": _("Agriculture, forestry, fisheries and veterinary"),
        "level_2_fields": {
            "081": {
                "name": _("Agriculture"),
                "level_3_fields": {"0811": _("Crop and livestock production"), "0812": _("Horticulture")},
            },
            "082": {"name": _("Forestry"), "level_3_fields": {"0821": _("Forestry")}},
            "083": {"name": _("Fisheries"), "level_3_fields": {"0831": _("Fisheries")}},
            "084": {"name": _("Veterinary"), "level_3_fields": {"0841": _("Veterinary")}},
        },
    },
    "09": {
        "name": _("Health and welfare"),
        "level_2_fields": {
            "091": {
                "name": _("Health"),
                "level_3_fields": {
                    "0911": _("Dental studies"),
                    "0912": _("Medicine"),
                    "0913": _("Nursing and midwifery"),
                    "0914": _("Medical diagnostic and treatment technology"),
                    "0915": _("Therapy and rehabilitation"),
                    "0916": _("Pharmacy"),
                    "0917": _("Traditional and complementary medicine and therapy"),
                },
            },
            "092": {
                "name": _("Welfare"),
                "level_3_fields": {
                    "0921": _("Care of the elderly and of disabled adults"),
                    "0922": _("Child care and youth services"),
                    "0923": _("Social work and counselling"),
                },
            },
        },
    },
    "10": {
        "name": _("Services"),
        "level_2_fields": {
            "101": {
                "name": _("Personal services"),
                "level_3_fields": {
                    "1011": _("Domestic services"),
                    "1012": _("Hair and beauty services"),
                    "1013": _("Hotel, restaurants and catering"),
                    "1014": _("Sports"),
                    "1015": _("Travel, tourism and leisure"),
                },
            },
            "102": {
                "name": _("Hygiene and occupational health services"),
                "level_3_fields": {"1021": _("Community sanitation"), "1022": _("Occupational health and safety")},
            },
            "103": {
                "name": _("Security services"),
                "level_3_fields": {"1031": _("Military and defence"), "1032": _("Protection of persons and property")},
            },
            "104": {"name": _("Transport services"), "level_3_fields": {"1041": _("Transport services")}},
        },
    },
}
