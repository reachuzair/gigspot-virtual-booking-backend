from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone
import os

from gigspot_backend import settings


def event_flyer_path(instance, filename):
    # Generate a unique filename for event flyers
    ext = filename.split('.')[-1]
    timestamp = int(timezone.now().timestamp())
    filename = f"event_flyer_{timestamp}.{ext}"
    return os.path.join('event_flyers', filename)


class Event(models.Model):
    """
    Model representing events at venues.
    """
    from custom_auth.models import PerformanceTier
    
    # Required Fields
    title = models.CharField(
        max_length=255,
        help_text='Title of the event'
    )
    
    artist_tier = models.CharField(
        max_length=20,
        choices=PerformanceTier.choices,
        help_text='Required tier for artists to book this event'
    )
    
    flyer_image = models.ImageField(
        upload_to=event_flyer_path,
        help_text='Background image/flyer for the event'
    )
    
    max_artists = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Maximum number of artists that can be booked'
    )
    
    ticket_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Price per ticket'
    )
    
    max_tickets = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Maximum number of tickets available'
    )
    
    venue_fee = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Fee charged by the venue'
    )
    
    booking_start = models.DateTimeField(
        help_text='Date and time when booking starts'
    )
    
    booking_end = models.DateTimeField(
        help_text='Date and time when booking ends'
    )
    
    # Auto fields
    created_by = models.ForeignKey(
        'custom_auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_events',
        help_text='User who created this event'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='liked_events',
        blank=True
    )
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return self.title
