from rest_framework import serializers
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest

from .models import Order, OrderItem
from products.models import Product

ALLOWED_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"refunded"},
    "refunded": {"pending"},
    "cancelled": {"pending"}, 
}

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    subtotal = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = OrderItem
        fields = ("id", "product", "product_name", "quantity", "unit_price", "subtotal")
        read_only_fields = ("id", "product_name", "subtotal", "unit_price")

    def get_subtotal(self, obj):
        return str(obj.subtotal)

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True)
    user = serializers.StringRelatedField(read_only=True)
    allowed_transitions = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id", "user", "status", "total", "note", "items",
            "allowed_transitions", "created_at", "updated_at",
        )
        read_only_fields = ("id", "user", "total", "status", "created_at", "updated_at")

    def get_allowed_transitions(self, obj):
        return sorted(list(ALLOWED_TRANSITIONS.get(obj.status, set())))

    # ---------- helpers ----------
    def _prod(self, raw) -> Product:
        if isinstance(raw, Product):
            return raw
        try:
            return Product.objects.get(pk=raw)
        except Product.DoesNotExist:
            raise serializers.ValidationError({"items": [f"product={raw} không tồn tại"]})

    def _qty(self, it) -> int:
        q = int(it.get("quantity", 1))
        if q <= 0:
            raise serializers.ValidationError({"items": ["quantity phải > 0"]})
        return q

    def _recalc_total(self, order: Order):
        total = sum(item.subtotal for item in order.items.all())
        order.total = total
        order.save(update_fields=["total"])
        return order

    @transaction.atomic
    def _reserve_stock(self, product: Product, qty: int):
        p = Product.objects.select_for_update().get(pk=product.pk)
        if p.stock < qty:
            raise serializers.ValidationError(
                {"items": [f"Sản phẩm '{p.name}' không đủ tồn (còn {p.stock}, cần {qty})."]}
            )
        Product.objects.filter(pk=p.pk).update(
            stock=F("stock") - qty,
            sold_count=F("sold_count") + qty,
        )

    @transaction.atomic
    def _release_stock(self, product: Product, qty: int):
        Product.objects.filter(pk=product.pk).update(
            stock=F("stock") + qty,
            sold_count=Greatest(F("sold_count") - qty, 0),
        )

    # ---------- create/update ----------
    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        request = self.context.get("request")
        order = Order.objects.create(user=request.user, **validated_data)

        for it in items_data:
            product = self._prod(it["product"])
            qty = self._qty(it)
            self._reserve_stock(product, qty)

        for it in items_data:
            product = self._prod(it["product"])
            qty = self._qty(it)
            OrderItem.objects.create(
                order=order, product=product, quantity=qty, unit_price=product.price
            )

        self._recalc_total(order)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if items_data is not None:
            for oi in list(instance.items.select_related("product")):
                self._release_stock(oi.product, oi.quantity)
            instance.items.all().delete()

            for it in items_data:
                product = self._prod(it["product"])
                qty = self._qty(it)
                self._reserve_stock(product, qty)
            for it in items_data:
                product = self._prod(it["product"])
                qty = self._qty(it)
                OrderItem.objects.create(
                    order=instance, product=product, quantity=qty, unit_price=product.price
                )

        self._recalc_total(instance)
        return instance
