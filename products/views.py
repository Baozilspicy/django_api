from rest_framework import viewsets, permissions
from rest_framework.permissions import AllowAny
from .models import Product
from .serializers import ProductSerializer
from common.permissions import IsAdminOrReadOnly   

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]

    # filter/search/ordering sẵn
    filterset_fields = []
    search_fields = ["name"]
    ordering_fields = ["price", "created_at"]
