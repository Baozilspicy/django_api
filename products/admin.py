from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id","name","price","stock","sold_count","created_at")
    search_fields = ("name",)
    list_editable = ("stock","price","name")
