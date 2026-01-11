from itertools import cycle

import pytest
from django.conf import settings
from mimesis.plugins.factory import FactoryField
from pytest_django import DjangoDbBlocker

from apps.account.models import User
from apps.store.models import Order
from apps.store.tests.factories import CartFactory, CouponFactory, ProductFactory


@pytest.mark.order(-1)
@pytest.mark.django_db
def test_store():
    ProductFactory.create_batch(3)
    CouponFactory.create_batch(3)
    CartFactory.create_batch(3)


@pytest.mark.order(-1)
@pytest.mark.load_data
def test_load_store_data(db_no_rollback: DjangoDbBlocker):
    with FactoryField.override_locale(settings.DEFAULT_LANGUAGE):
        # product
        products = ProductFactory.create_batch(14)

        # coupon
        coupons = CouponFactory.create_batch(len(products))

        # cart
        users = User.objects.all()[:5]
        carts = set()
        for coupon, product, user in zip(coupons, products, cycle(users)):
            cart = CartFactory(user=user)
            cart.products.add(product)
            carts.add(cart)

        orders = []
        for cart in carts:
            if cart.active:
                orders.append(Order.create_from_cart(cart, coupon_codes=[coupon.code], dry_run=False))
