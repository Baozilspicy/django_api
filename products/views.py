from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from .models import Product
from .serializers import ProductSerializer

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [AllowAny]  

    # filter/search/ordering sẵn
    filterset_fields = []
    search_fields = ["name"]
    ordering_fields = ["price", "created_at"]
