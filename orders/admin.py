# orders/admin.py
from django.contrib import admin
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Greatest

from .models import Order, OrderItem
from products.models import Product


# ----------------- Helpers -----------------
def _release_all_stock(order: Order):
    """Trả kho toàn bộ item của 1 đơn."""
    for it in order.items.all():
        Product.objects.filter(pk=it.product_id).update(
            stock=F("stock") + it.quantity,
            sold_count=Greatest(F("sold_count") - it.quantity, 0),
        )


def _reserve_all_stock(order: Order):
    """Giữ kho cho toàn bộ item của 1 đơn. Trả None nếu OK; ngược lại trả về thông báo lỗi."""
    # check trước
    for it in order.items.select_related("product"):
        p = Product.objects.select_for_update().get(pk=it.product_id)
        if p.stock < it.quantity:
            return f"'{p.name}' thiếu kho (còn {p.stock}, cần {it.quantity})"
    # giữ kho
    for it in order.items.all():
        Product.objects.filter(pk=it.product_id).update(
            stock=F("stock") - it.quantity,
            sold_count=F("sold_count") + it.quantity,
        )
    return None


def _apply_stock_diff(product_id: int, diff: int):
    """diff>0: bán thêm (trừ); diff<0: trả bớt (cộng)."""
    if diff == 0:
        return
    if diff > 0:
        Product.objects.filter(pk=product_id).update(
            stock=F("stock") - diff, sold_count=F("sold_count") + diff
        )
    else:
        Product.objects.filter(pk=product_id).update(
            stock=F("stock") + (-diff),
            sold_count=Greatest(F("sold_count") - (-diff), 0),
        )


# ----------------- Admin actions (dùng với dropdown + Go) -----------------
@admin.action(description="Đánh dấu Paid")
def action_mark_paid(modeladmin, request, queryset):
    for o in queryset.filter(status="pending"):
        o.status = "paid"
        o.save(update_fields=["status"])


@admin.action(description="Hủy đơn (trả kho)")
@transaction.atomic
def action_cancel(modeladmin, request, queryset):
    # chỉ cho cancel từ pending
    for o in queryset.filter(status="pending"):
        _release_all_stock(o)
        o.status = "cancelled"
        o.save(update_fields=["status"])


@admin.action(description="Hoàn tiền (paid → refunded) + trả kho")
@transaction.atomic
def action_refund(modeladmin, request, queryset):
    for o in queryset.filter(status="paid"):
        _release_all_stock(o)
        o.status = "refunded"
        o.save(update_fields=["status"])


@admin.action(description="Mở lại đơn (cancelled/refunded → pending, giữ kho)")
@transaction.atomic
def action_reopen(modeladmin, request, queryset):
    for o in queryset.filter(status__in=["cancelled", "refunded"]):  
        err = _reserve_all_stock(o)
        if err:
            modeladmin.message_user(
                request, f"Không mở lại Order #{o.id}: {err}", level=30  
            )
            continue
        o.status = "pending"
        o.save(update_fields=["status"])


# ----------------- Inline -----------------
class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "quantity", "unit_price")
    can_delete = True  # tick DELETE để xóa dòng

    # Chỉ cho sửa/thêm/xóa item khi order đang pending
    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or obj.status == "pending")

    def has_add_permission(self, request, obj):
        return super().has_add_permission(request, obj) and (obj is None or obj.status == "pending")

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or obj.status == "pending")


# ----------------- OrderAdmin -----------------
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "total", "created_at", "items_summary")
    list_filter = ("status",)
    search_fields = ("user__username",)
    inlines = [OrderItemInline]

    # CHỈ GIỮ ACTIONS (không list_editable → không còn nút Save ở list)
    actions = [action_mark_paid, action_cancel, action_refund, action_reopen]

    # Khóa các trường tổng hợp / tự quản
    readonly_fields = ("status", "total", "created_at", "updated_at", "user")

    def items_summary(self, obj):
        rows = [f"{it.product.name} x{it.quantity}" for it in obj.items.select_related("product")[:3]]
        more = obj.items.count() - 3
        return ", ".join(rows) + (f" (+{more}…)" if more > 0 else "")
    items_summary.short_description = "Items"

    # Cập nhật stock & total khi sửa OrderItem trong trang chi tiết
    @transaction.atomic
    def save_formset(self, request, form, formset, change):
        if formset.model is not OrderItem:
            return super().save_formset(request, form, formset, change)

        for obj in formset.deleted_objects:
            _apply_stock_diff(obj.product_id, -obj.quantity)
            obj.delete()

        instances = formset.save(commit=False)
        for inst in instances:
            is_new = inst.pk is None
            old_qty, old_pid = 0, inst.product_id
            if not is_new:
                old = OrderItem.objects.only("quantity", "product_id").get(pk=inst.pk)
                old_qty, old_pid = old.quantity, old.product_id

            inst.save()

            if is_new:
                _apply_stock_diff(inst.product_id, inst.quantity)
            else:
                if inst.product_id != old_pid:
                    _apply_stock_diff(old_pid, -old_qty)
                    _apply_stock_diff(inst.product_id, inst.quantity)
                else:
                    diff = inst.quantity - old_qty
                    _apply_stock_diff(inst.product_id, diff)

        formset.save_m2m()

        o = form.instance
        o.total = sum(i.quantity * i.unit_price for i in o.items.all())
        o.save(update_fields=["total"])

    # Restock khi xoá Order trong admin
    @transaction.atomic
    def delete_model(self, request, obj):
        _release_all_stock(obj)
        return super().delete_model(request, obj)

    # Restock khi xoá hàng loạt Order trong admin
    @transaction.atomic
    def delete_queryset(self, request, queryset):
        for o in queryset:
            _release_all_stock(o)
        return super().delete_queryset(request, queryset)
