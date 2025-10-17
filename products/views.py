from rest_framework import viewsets
from .models import Product
from .serializers import ProductSerializer,ProductInfoSerializer
from common.permissions import IsAdminOrReadOnly   

from rest_framework.response import Response          
from rest_framework.decorators import action          
from django.db.models import Max

class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnly]

    # filter/search/ordering sẵn -> bình thường là filter hết, như này để giới hạn
    filterset_fields = []
    search_fields = ["name"]
    ordering_fields = ["price", "created_at"]

    #detail=false tức là ko cần {id}
    @action(detail=False, methods=["get"])
    def info(self, request):
        qs = self.filter_queryset(self.get_queryset())
        payload = {
            "products": qs,                     
            "count": qs.count(),
            "max_price": qs.aggregate(m=Max("price"))["m"],
        }
        ser = ProductInfoSerializer(payload, context={"request": request})
        return Response(ser.data)