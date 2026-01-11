import itertools
from typing import TYPE_CHECKING

import mimesis
from django.conf import settings
from django.core.files.base import ContentFile
from django.db.models import QuerySet
from django.utils import timezone
from factory.declarations import Iterator, LazyAttribute, LazyFunction
from factory.django import DjangoModelFactory
from factory.helpers import post_generation
from mimesis.plugins.factory import FactoryField

from apps.account.models import User
from apps.learning.models import ENROLLABLE_MODELS
from apps.operation.models import Category
from apps.store.models import Cart, Coupon, Product, ProductItem

generic = mimesis.Generic(settings.DEFAULT_LANGUAGE)

if TYPE_CHECKING:
    from django.db.models.fields.related_descriptors import ManyRelatedManager


def get_item_type_cycle():
    return itertools.cycle(ENROLLABLE_MODELS)


ITEM_TYPE_MODEL_CYCLE = get_item_type_cycle()


class ProductFactory(DjangoModelFactory[Product]):
    status = Product.StatusChoices.PUBLISHED
    name = FactoryField("text.title")
    description = FactoryField("text")
    thumbnail = LazyFunction(
        lambda: ContentFile(
            generic.binaryfile.image(file_type=mimesis.ImageFile.PNG),
            f"thumbnail.{generic.random.randint(0, 1000)}.png",
        )
    )
    price = FactoryField("choice", items=[10000, 20000, 30000])
    display_price = FactoryField("choice", items=[10000 * 10, 20000 * 10, 30000 * 10])

    class Meta:
        model = Product
        django_get_or_create = ("name",)
        skip_postgeneration_save = True

    if TYPE_CHECKING:
        productitem_set: QuerySet[ProductItem]
        categories: ManyRelatedManager

    @post_generation
    def post_generation(self, create, extracted, **kwargs):
        if not create:
            return

        if self.productitem_set.exists():
            return

        self.categories.set(Category.objects.filter(depth=3).order_by("?")[: generic.random.randint(1, 2)])

        # product items
        Model = next(ITEM_TYPE_MODEL_CYCLE)

        # samples
        items: "QuerySet" = Model.objects.order_by("?")[: generic.random.randint(1, 3)]
        if items:
            ProductItem.objects.bulk_create(
                [ProductItem(product=self, validity_days=90, item=item, ordering=i) for i, item in enumerate(items)],
                ignore_conflicts=True,
            )


class CouponFactory(DjangoModelFactory[Coupon]):
    kind = Iterator(Coupon.KindChoices)
    code = LazyFunction(lambda: f"{generic.cryptographic.uuid()[:12]}")
    name = FactoryField("fruit")
    description = FactoryField("text")
    discount_value = LazyAttribute(lambda o: 50 if o.kind == Coupon.KindChoices.PERCENTAGE else 20000)
    min_order_price = 5000
    usage_limit = 100
    active = True
    valid_from = LazyAttribute(lambda o: timezone.now())

    class Meta:
        model = Coupon
        django_get_or_create = ("code",)


class CartFactory(DjangoModelFactory[Cart]):
    user = Iterator(User.objects.all()[:5])
    active = True

    if TYPE_CHECKING:
        products: ManyRelatedManager

    class Meta:
        model = Cart
        django_get_or_create = ("user",)
