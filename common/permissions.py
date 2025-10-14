from rest_framework.permissions import BasePermission, SAFE_METHODS

class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        # GET/HEAD/OPTIONS: ai cũng xem được (kể cả chưa đăng nhập)
        if request.method in SAFE_METHODS:
            return True
        # Các method ghi: POST/PUT/PATCH/DELETE chỉ admin (is_staff) mới được
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)