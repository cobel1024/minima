from decimal import Decimal
from typing import TYPE_CHECKING

import pghistory
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    Count,
    DateTimeField,
    DecimalField,
    EmailField,
    ForeignKey,
    ImageField,
    Index,
    JSONField,
    ManyToManyField,
    Model,
    PositiveSmallIntegerField,
    Q,
    QuerySet,
    TextChoices,
    TextField,
    UniqueConstraint,
)
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField

from apps.common.models import OrderableMixin, TimeStampedMixin, tuid
from apps.operation.models import Category, TaggableMixin

User = get_user_model()


if TYPE_CHECKING:
    from apps.account.models import User


ZERO = Decimal("0.0")


@pghistory.track()
class Product(TimeStampedMixin, TaggableMixin):
    class StatusChoices(TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        ARCHIVED = "archived", _("Archived")

    status = CharField(_("Status"), max_length=20, choices=StatusChoices.choices)
    name = CharField(_("Name"), max_length=255, unique=True)
    description = TextField(_("Description"), blank=True, default="")
    thumbnail = ImageField(_("Thumbnail"))
    categories = ManyToManyField(Category, blank=True, verbose_name=_("Categories"))
    price = DecimalField(_("Price"), max_digits=10, decimal_places=2)
    display_price = DecimalField(_("Display Price"), max_digits=10, decimal_places=2)

    class Meta(TimeStampedMixin.Meta, TaggableMixin.Meta):
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        indexes = [Index(fields=["status"])]

    if TYPE_CHECKING:
        pk: int
        productitem_set: "QuerySet[ProductItem]"

    def __str__(self):
        return self.name


@pghistory.track()
class ProductItem(TimeStampedMixin, OrderableMixin):
    product = ForeignKey(Product, CASCADE, verbose_name=_("Product"))
    validity_days = PositiveSmallIntegerField(_("Validity Days"), default=60)
    item_type = ForeignKey(ContentType, CASCADE, verbose_name=_("Item Type"))
    item_id = CharField(_("Item ID"), max_length=36)
    item = GenericForeignKey("item_type", "item_id")

    ordering_group = ("product",)

    class Meta(TimeStampedMixin.Meta, OrderableMixin.Meta):
        verbose_name = _("Product Item")
        verbose_name_plural = _("Product Items")
        indexes = [Index(fields=["item_type", "item_id"])]
        constraints = [
            UniqueConstraint(fields=["product", "item_type", "item_id"], name="store_productitem_pr_itty_itid_uniq")
        ]


@pghistory.track()
class Coupon(TimeStampedMixin):
    class KindChoices(TextChoices):
        PERCENTAGE = "percentage", _("Percentage")
        FIXED = "fixed", _("Fixed")

    kind = CharField(_("Kind"), max_length=20, choices=KindChoices.choices)
    code = CharField(_("Code"), max_length=24, unique=True)
    name = CharField(_("Name"), max_length=50)
    description = TextField(_("Description"), blank=True, default="")
    discount_value = DecimalField(_("Discount Value"), max_digits=10, decimal_places=2)
    min_order_price = DecimalField(_("Minimum Order Price"), max_digits=10, decimal_places=2)
    usage_limit = PositiveSmallIntegerField(_("Usage Limit"))
    active = BooleanField(_("Active"), default=True)
    valid_from = DateTimeField(_("Valid From"), default=timezone.now)
    valid_until = DateTimeField(_("Valid Until"), null=True, blank=True)
    applicable_products = ManyToManyField(Product, blank=True, verbose_name=_("Applicable Products"))
    excluded_products = ManyToManyField(Product, blank=True, related_name="+", verbose_name=_("Excluded Products"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Coupon")
        verbose_name_plural = _("Coupons")

    if TYPE_CHECKING:
        ordercoupon_set: "QuerySet[OrderCoupon]"
        ordercoupon_count: int

    def is_applicable_to_product(self, product: "Product"):
        if self.excluded_products.filter(id=product.pk).exists():
            return False

        if self.applicable_products.filter(id=product.pk).exists():
            return True

        return not self.applicable_products.exists()

    def calculate_discount_for_product(self, product_price: Decimal):
        if self.kind == self.KindChoices.PERCENTAGE.value:
            return product_price * (self.discount_value / 100)
        else:
            return self.discount_value

    def clean(self):
        super().clean()
        if self.kind == self.KindChoices.PERCENTAGE.value:
            if not (0 < self.discount_value <= 100):
                raise ValidationError(_("Percentage must be between 1 and 100"))
        elif self.kind == self.KindChoices.FIXED.value:
            if self.discount_value <= 0:
                raise ValidationError(_("Fixed discount must be positive"))


@pghistory.track()
class Cart(TimeStampedMixin):
    user = ForeignKey(User, CASCADE, verbose_name=_("User"))
    active = BooleanField(_("Active"), default=True)
    products = ManyToManyField(Product, blank=True, through="CartProduct", verbose_name=_("Products"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Cart")
        verbose_name_plural = _("Carts")
        constraints = [UniqueConstraint(fields=["user"], condition=Q(active=True), name="unique_active_cart_per_user")]

    if TYPE_CHECKING:
        cartproduct_set: "QuerySet[CartProduct]"

    def deactivate(self):
        self.active = False
        self.save(update_fields=["active"])


@pghistory.track()
class CartProduct(TimeStampedMixin):
    cart = ForeignKey(Cart, CASCADE, verbose_name=_("Cart"))
    product = ForeignKey(Product, CASCADE, verbose_name=_("Product"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Cart Product")
        verbose_name_plural = _("Cart Products")
        constraints = [UniqueConstraint(fields=["cart", "product"], name="store_cartproduct_ca_pr_uniq")]


@pghistory.track()
class Order(TimeStampedMixin):
    class StatusChoices(TextChoices):
        PENDING = "pending", _("Pending")
        PAID = "paid", _("Paid")
        CANCELED = "canceled", _("Canceled")
        FAILED = "failed", _("Failed")
        REFUNDED = "refunded", _("Refunded")

    status = CharField(_("Status"), max_length=20, choices=StatusChoices.choices)
    customer = ForeignKey(User, CASCADE, verbose_name=_("Customer"))
    order_number = CharField(_("Order Number"), max_length=24, unique=True)
    subtotal = DecimalField(_("Subtotal"), max_digits=10, decimal_places=2)
    total_discount = DecimalField(_("Total Discount"), max_digits=10, decimal_places=2)
    total_amount = DecimalField(_("Total Amount"), max_digits=10, decimal_places=2)
    customer_name = CharField(_("Customer Name"), max_length=100)
    customer_email = EmailField(_("Customer Email"))
    customer_phone = PhoneNumberField(_("Customer Phone"), null=True, blank=True)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Order")
        verbose_name_plural = _("Orders")
        indexes = [Index(fields=["status"]), Index(fields=["customer_name"]), Index(fields=["customer_email"])]

    if TYPE_CHECKING:
        orderproduct_set: "QuerySet[OrderProduct]"

    @classmethod
    def create_from_cart(cls, cart: "Cart", coupon_codes: list[str], dry_run: bool):
        if not cart.active:
            raise ValidationError(_("Cart is not active"))

        customer = cart.user
        order_props = {
            "customer": customer,
            "customer_name": customer.name,
            "customer_email": customer.email,
            "customer_phone": customer.phone,
            "subtotal": ZERO,
            "total_discount": ZERO,
            "total_amount": ZERO,
            "order_number": tuid() if not dry_run else None,
        }

        order = cls.objects.create(**order_props) if not dry_run else cls(**order_props, id=0)

        order_products = [
            OrderProduct(
                order=order,
                product=cp.product,
                product_name=cp.product.name,
                price=cp.product.price,
                discount_amount=ZERO,
            )
            for cp in cart.cartproduct_set.select_related("product").filter(
                product__status=Product.StatusChoices.PUBLISHED
            )
        ]

        if not dry_run:
            order_products = OrderProduct.objects.bulk_create(order_products)

        setattr(order, "_prefetched_objects_cache", {"orderproduct_set": order_products})

        if coupon_codes:
            order.apply_coupons(coupon_codes, dry_run=dry_run)

        order.calculate_totals()

        if not dry_run:
            order.save(update_fields=["subtotal", "total_discount", "total_amount"])
            cart.deactivate()

        return order

    def apply_coupons(self, coupon_codes: list[str], dry_run: bool = True):
        if not coupon_codes:
            return

        # _prefetched_objects_cache
        order_products = self.orderproduct_set.all()
        original_subtotal = sum((op.price for op in order_products), ZERO)

        valid_coupons = (
            Coupon.objects
            .annotate(ordercoupon_count=Count("ordercoupon"))
            .filter(
                Q(valid_until__isnull=True) | Q(valid_until__gte=timezone.now()),
                code__in=coupon_codes,
                active=True,
                valid_from__lte=timezone.now(),
            )
            .prefetch_related("applicable_products", "excluded_products")
        )

        applicable_coupons: "list[Coupon]" = []
        for coupon in valid_coupons:
            if original_subtotal < coupon.min_order_price:
                raise ValidationError(
                    _("%(coupon_code)s does not meet the minimum order price %(min_order_price)s.")
                    % {"coupon_code": coupon.code, "min_order_price": coupon.min_order_price}
                )

            if coupon.usage_limit > 0 and coupon.ordercoupon_count >= coupon.usage_limit:
                raise ValidationError(
                    _("%(coupon_code)s has reached its usage limit %(usage_limit)s.")
                    % {"coupon_code": coupon.code, "usage_limit": coupon.usage_limit}
                )

            applicable_coupons.append(coupon)

        if not dry_run:
            OrderCoupon.objects.bulk_create([OrderCoupon(order=self, coupon=coupon) for coupon in applicable_coupons])

        for order_product in order_products:
            discount_amount = ZERO

            for coupon in applicable_coupons:
                if coupon.is_applicable_to_product(order_product.product):
                    discount_amount += coupon.calculate_discount_for_product(order_product.price)

            order_product.discount_amount = min(discount_amount, order_product.price)

        if not dry_run:
            OrderProduct.objects.bulk_update(order_products, fields=["discount_amount"])

    def calculate_totals(self):
        products = self.orderproduct_set.all()
        self.subtotal = sum((op.price for op in products), ZERO)
        self.total_discount = sum((op.discount_amount for op in products), ZERO)
        self.total_amount = max(self.subtotal - self.total_discount, ZERO)


@pghistory.track()
class OrderProduct(TimeStampedMixin):
    order = ForeignKey(Order, CASCADE, verbose_name=_("Order"))
    product = ForeignKey(Product, CASCADE, verbose_name=_("Product"))

    # snapshot
    product_name = CharField(_("Product Name"), max_length=255)
    price = DecimalField(_("Price"), max_digits=10, decimal_places=2)
    discount_amount = DecimalField(_("Discount Amount"), max_digits=10, decimal_places=2)

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Order Product")
        verbose_name_plural = _("Order Products")

    if TYPE_CHECKING:
        product_id = int()


@pghistory.track()
class OrderCoupon(OrderableMixin):
    order = ForeignKey(Order, CASCADE, verbose_name=_("Order"))
    coupon = ForeignKey(Coupon, CASCADE, verbose_name=_("Coupon"))

    ordering_group = ("order",)

    class Meta:
        verbose_name = _("Order Coupon")
        verbose_name_plural = _("Order Coupons")
        constraints = [UniqueConstraint(fields=["order", "coupon"], name="store_ordercoupon_or_co_uniq")]


@pghistory.track()
class Gateway(Model):
    name = CharField(_("Name"), max_length=100, unique=True)
    store_id = CharField(_("Store ID"), max_length=100)
    expires = DateTimeField(_("Expires"), null=True, blank=True)

    class Meta:
        verbose_name = _("Payment Gateway")
        verbose_name_plural = _("Payment Gateways")


@pghistory.track()
class Payment(TimeStampedMixin):
    class StatusChoices(TextChoices):
        READY = "ready", _("Ready")
        PENDING = "pending", _("Pending")
        PARTIAL = "partial", _("Partial")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")
        CANCELED = "canceled", _("Canceled")

    status = CharField(_("Status"), max_length=20, choices=StatusChoices.choices)
    order = ForeignKey(Order, CASCADE, verbose_name=_("Order"))
    transaction_id = CharField(_("Transaction ID"), max_length=100, unique=True)
    amount = DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    gateway = ForeignKey(Gateway, CASCADE, verbose_name=_("Gateway"))
    payment_data = JSONField(_("Payment Data"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Payment")
        verbose_name_plural = _("Payments")
        indexes = [Index(fields=["status"])]


@pghistory.track()
class Refund(TimeStampedMixin):
    class StatusChoices(TextChoices):
        PENDING = "pending", _("Pending")
        COMPLETED = "completed", _("Completed")
        FAILED = "failed", _("Failed")

    status = CharField(_("Status"), max_length=20, choices=StatusChoices.choices)
    payment = ForeignKey(Payment, CASCADE, verbose_name=_("Payment"))
    refund_id = CharField(_("Refund ID"), max_length=100)
    amount = DecimalField(_("Amount"), max_digits=10, decimal_places=2)
    reason = TextField(_("Reason"))
    refund_data = JSONField(_("Refund Data"), blank=True, default=dict)
    processed_by = ForeignKey(User, CASCADE, verbose_name=_("Processed By"))

    class Meta(TimeStampedMixin.Meta):
        verbose_name = _("Refund")
        verbose_name_plural = _("Refunds")
        indexes = [Index(fields=["status"])]
