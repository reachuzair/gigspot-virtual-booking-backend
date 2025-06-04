from django.db import models
from django.core.validators import MinValueValidator
from custom_auth.models import Artist, Venue, User, PerformanceTier
from django.utils import timezone
import os

def event_flyer_path(instance, filename):
    # Generate a unique filename for event flyers
    ext = filename.split('.')[-1]
    timestamp = int(timezone.now().timestamp())
    filename = f"event_flyer_{timestamp}.{ext}"
    return os.path.join('event_flyers', filename)

# Create your models here.

class Status(models.TextChoices):
    PENDING = 'pending', 'Pending'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Rejected'
    
class GenreChoices(models.TextChoices):
    RAP = 'rap', 'Rap'
    HIP_HOP = 'hip_hop', 'Hip Hop'
    POP = 'pop', 'Pop'
    

class GigType(models.TextChoices):
    ARTIST_GIG = 'artist_gig', 'Artist Gig'  # Created by artist
    VENUE_GIG = 'venue_gig', 'Venue Gig'     # Created by venue

class Gig(models.Model):
    id = models.AutoField(primary_key=True)
    # Gig type and basic info
    gig_type = models.CharField(max_length=20, choices=GigType.choices, default=None)
    # Core fields
    title = models.CharField(max_length=255, help_text='Title of the gig/event', default="")
    description = models.TextField(blank=True, null=True, default="")
    event_date = models.DateTimeField(default=timezone.now)
    booking_start_date = models.DateTimeField(null=True, blank=True)
    booking_end_date = models.DateTimeField(null=True, blank=True)
    
    # Media
    flyer_image = models.ImageField(upload_to=event_flyer_path, blank=True, null=True)
    
    # Relationships
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_gigs', default=None, null=True, blank=True)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='gigs', null=True, blank=True)
    collaborators = models.ManyToManyField(
        User,
        related_name='collaborative_gigs',
        blank=True
    )
    invitees = models.ManyToManyField(
        'users.Artist',
        related_name='invited_gigs',
        blank=True
    )
    
    # Artist requirements
    minimum_performance_tier = models.CharField(
        max_length=255, 
        choices=PerformanceTier.choices, 
        default=PerformanceTier.FRESH_TALENT,
        help_text='Minimum performance tier required for artists',
        null=True,
        blank=True
    )
    
    # Capacity
    max_artists = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        default=1,
        help_text='Maximum number of artists that can participate',
        null=True,
        blank=True
    )
    max_tickets = models.PositiveIntegerField(
        default=100,
        validators=[MinValueValidator(1)],
        help_text='Maximum number of tickets available',
        null=True,
        blank=True
    )
    
    # Financials
    ticket_price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.0,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    venue_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.0,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    
    # Status and metadata
    status = models.CharField(
        max_length=20, 
        choices=Status.choices, 
        default=Status.PENDING,
        help_text='Current status of the gig'
    )
    gig_type = models.CharField(
        max_length=20,
        choices=GigType.choices,
        default=GigType.ARTIST_GIG,
        help_text='Type of gig (artist-created or venue-created)'
    )
    is_public = models.BooleanField(default=True)
    sold_out = models.BooleanField(default=False)
    slot_available = models.BooleanField(default=True)
    
    # Artist-specific fields (for gigs created by artists)
    request_message = models.TextField(blank=True, null=True, default="")
    invitees = models.ManyToManyField(Artist, related_name='invited_gigs', blank=True)
    collaborators = models.ManyToManyField(Artist, related_name='collaborated_gigs', blank=True)
    likes = models.ManyToManyField(User, related_name='liked_gigs', blank=True)
    
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    @property
    def name(self):
        return self.title
        
    @name.setter
    def name(self, value):
        self.title = value
        
    @property
    def flyer_bg(self):
        return self.flyer_image
        
    @flyer_bg.setter
    def flyer_bg(self, value):
        self.flyer_image = value

    def save(self, *args, **kwargs):
        # Set expires_at to 10 minutes after created_at if not already set
        if not self.expires_at and self.created_at:
            self.expires_at = self.created_at + timezone.timedelta(minutes=10)
        super(Gig, self).save(*args, **kwargs)


    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Gig'
        verbose_name_plural = 'Gigs'

class Contract(models.Model):
    id = models.AutoField(primary_key=True)
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE, related_name='contracts', default=None, null=True, blank=True)
    venue_signed = models.BooleanField(default=False)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='contracts', default=None, null=True, blank=True)
    artist_signed = models.BooleanField(default=False)
    pdf = models.FileField(upload_to='gigs/contracts/', blank=True, null=True)
    image = models.ImageField(upload_to='gigs/contracts/', blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.0)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'

class GigInviteStatus(models.TextChoices):
    PENDING = 'pending', 'Pending'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'

class GigInvite(models.Model):
    gig = models.ForeignKey('Gig', on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='gig_invites_sent', default=None, null=True, blank=True)
    artist_received = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name='gig_invites_received')
    status = models.CharField(max_length=255, choices=GigInviteStatus.choices, default=GigInviteStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
