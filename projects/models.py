from django.db import models
from users.models import Profile
import uuid
# Create your models here.
class Projects(models.Model):
    owner = models.ForeignKey(Profile, on_delete=models.CASCADE, null=True, blank=True, related_name="projects")
    title = models.CharField(max_length=240)
    decription = models.TextField(null=True, blank=True)
    website_link = models.CharField(max_length=2000, null=True, blank=True)
    status = models.CharField(max_length=240, choices=[('pending', 'Pending'), ('proccessing', 'Processing'), ('ready', 'Ready'), ('failed', 'Failed')])
    cleaned_zip = models.FileField(null=True, blank=True, upload_to='zips/')
    created = models.DateTimeField(auto_now_add=True)
    id = models.UUIDField(default=uuid.uuid4, unique=True, primary_key=True, editable=False)

    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['created']