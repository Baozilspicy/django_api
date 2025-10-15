from django.db import transaction
from django.db.models import F
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status as http_status

from .models import Order
from .serializers import OrderSerializer
from products.models import Product

ALLOWED_TRANSITIONS = {
    "draft": {"pending", "cancelled"},
    "pending": {"paid", "cancelled"},
    "paid": {"refunded"},
    "refunded": {"reopened"},
    "cancelled": {"reopened"},   
}

class IsOwnerOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.user.is_staff or obj.user_id == request.user.id

class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
    search_fields = ["note"]
    ordering_fields = ["created_at", "total"]
    filterset_fields = {"status": ["exact"]}

    def get_queryset(self):
        qs = Order.objects.select_related("user").prefetch_related("items__product")
        return qs if self.request.user.is_staff else qs.filter(user=self.request.user)

    # ------- helpers -------
    def _reserve_all(self, order: Order):
        for it in order.items.select_related("product"):
            p = Product.objects.select_for_update().get(pk=it.product_id)
            if p.stock < it.quantity:
                return f"'{p.name}' thiếu kho (còn {p.stock}, cần {it.quantity})"
        for it in order.items.all():
            Product.objects.filter(pk=it.product_id).update(
                stock=F("stock") - it.quantity, sold_count=F("sold_count") + it.quantity
            )
        return None

    def _release_all(self, order: Order):
        for it in order.items.all():
            Product.objects.filter(pk=it.product_id).update(
                stock=F("stock") + it.quantity, sold_count=F("sold_count") - it.quantity
            )

    # ------- actions -------
    @action(detail=True, methods=["post"])
    def pay(self, request, pk=None):
        o = self.get_object()
        if o.status != "pending":
            return Response({"detail": "Chỉ pay từ pending"}, status=400)
        o.status = "paid"; o.save(update_fields=["status"])
        return Response(self.get_serializer(o).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def cancel(self, request, pk=None):
        o = self.get_object()
        if o.status not in ("draft","pending"):
            return Response({"detail":"Chỉ hủy từ draft/pending"}, status=400)
        self._release_all(o)
        o.status = "cancelled"; o.save(update_fields=["status"])
        return Response(self.get_serializer(o).data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def refund(self, request, pk=None):
        o = self.get_object()
        if o.status != "paid":
            return Response({"detail":"Chỉ hoàn tiền đơn đã paid"}, status=400)
        self._release_all(o)
        o.status = "refunded"; o.save(update_fields=["status"])
        return Response(self.get_serializer(o).data, status=http_status.HTTP_200_OK)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    @transaction.atomic
    def reopen(self, request, pk=None):
        o = self.get_object()
        if o.status != "cancelled":
            return Response({"detail":"Chỉ mở lại đơn đã hủy"}, status=400)
        err = self._reserve_all(o)
        if err:
            return Response({"detail": err}, status=400)
        o.status = "pending"; o.save(update_fields=["status"])
        return Response(self.get_serializer(o).data, status=200)

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    @transaction.atomic
    def reopen(self, request, pk=None):
        """
        cancelled/refunded -> pending (mở lại, giữ kho; fail nếu thiếu).
        """
        o = self.get_object()
        if o.status not in ("cancelled", "refunded"):
            return Response({"detail": "Chỉ mở lại đơn đã hủy/đã hoàn tiền"}, status=400)

        err = self._reserve_all(o)   # giữ kho lại cho các items
        if err:
            return Response({"detail": err}, status=400)

        o.status = "pending"
        o.save(update_fields=["status"])
        return Response(self.get_serializer(o).data, status=200)