from django.db import models

# Create your models here.

class STATUS_CHOICES(models.TextChoices):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'

class Connection(models.Model):
    artist = models.ForeignKey('custom_auth.Artist', on_delete=models.CASCADE, related_name='connections_sent')
    connected_artist = models.ForeignKey('custom_auth.Artist', on_delete=models.CASCADE, related_name='connections_received')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES.choices, default=STATUS_CHOICES.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Connection'
        verbose_name_plural = 'Connections'
        