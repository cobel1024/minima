from django.contrib import admin

from apps.common.admin import HiddenModelAdmin, ModelAdmin, TabularInline
from apps.store.models import (
    Cart,
    CartProduct,
    Coupon,
    Gateway,
    Order,
    OrderCoupon,
    OrderProduct,
    Payment,
    Product,
    ProductItem,
    Refund,
)


@admin.register(Product)
class ProductAdmin(ModelAdmin[Product]):
    class ProductItemInline(TabularInline[ProductItem]):
        model = ProductItem
        ordering = ("ordering", "id")
        ordering_field = "ordering"

    inlines = (ProductItemInline,)


@admin.register(Order)
class OrderAdmin(ModelAdmin[Order]):
    class OrderProductInline(TabularInline[OrderProduct]):
        model = OrderProduct

    class OrderCouponInline(TabularInline[OrderCoupon]):
        model = OrderCoupon

    inlines = (OrderProductInline, OrderCouponInline)


@admin.register(Cart)
class CartAdmin(ModelAdmin[Cart]):
    class CartProductInline(TabularInline[CartProduct]):
        model = CartProduct

    inlines = (CartProductInline,)


@admin.register(Coupon)
class CouponAdmin(ModelAdmin[Coupon]):
    pass


@admin.register(Gateway)
class GatewayAdmin(ModelAdmin[Gateway]):
    pass


@admin.register(Payment)
class PaymentAdmin(ModelAdmin[Payment]):
    class RefundInline(TabularInline[Refund]):
        model = Refund

    inlines = (RefundInline,)


@admin.register(ProductItem)
class ProductItemAdmin(HiddenModelAdmin[ProductItem]):
    pass


@admin.register(CartProduct)
class CartProductAdmin(HiddenModelAdmin[CartProduct]):
    pass


@admin.register(OrderProduct)
class OrderProductAdmin(HiddenModelAdmin[OrderProduct]):
    pass


@admin.register(OrderCoupon)
class OrderCouponAdmin(HiddenModelAdmin[OrderCoupon]):
    pass


@admin.register(Refund)
class RefundAdmin(ModelAdmin[Refund]):
    pass
