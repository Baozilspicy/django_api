from django.db import models
from products.models import Product
from django.conf import settings

class Order(models.Model):
    STATUS_PENDING   = "pending"
    STATUS_PAID      = "paid"
    STATUS_REFUNDED  = "refunded"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_REFUNDED, "Refunded"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status     = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)  # 👈 mặc định pending
    note       = models.TextField(blank=True, default="")
    total      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order#{self.id} by {self.user.username}"

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    # chụp lại giá ở thời điểm đặt hàng
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["order", "product"], name="uniq_order_product")
        ]

    @property
    def subtotal(self):
        return self.quantity * self.unit_price
