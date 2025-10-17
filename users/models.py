from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):

    phone = models.CharField(max_length=11, unique=True)

    # Tuỳ chọn hoặc user sẽ nhập sau sau khi thành công tạo acc
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.username} ({self.phone})" if self.phone else self.username
    #cần hỏi lại