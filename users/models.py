from django.db import models

# Create your models here.

class UserSettings(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField('custom_auth.User', on_delete=models.CASCADE, related_name='settings')
    notify_by_app = models.BooleanField(default=True)
    notify_by_email = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} Settings"
    
