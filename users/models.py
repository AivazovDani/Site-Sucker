from django.db import models

# Create your models here.
import uuid
from django.contrib.auth.models import User



class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    username = models.CharField(max_length=20, null=True, blank=True)
    email = models.EmailField(max_length=40, null=True, blank=True)
    image_profile = models.ImageField(null=True, blank=True, upload_to='images/')
    created = models.DateTimeField(auto_now_add=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)


    def __str__(self):
        return self.username
    
    class Meta:
        ordering = ['created']