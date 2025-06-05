from django.db import models
from django.core.validators import MinValueValidator
from custom_auth.models import Artist, Venue, User, PerformanceTier
from django.utils import timezone
from .utils import validate_ticket_price, PricingValidationError
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
        related_name='collaborated_gigs_artist',
        blank=True,
        help_text='Artists who are collaborating on this gig'
    )
    invitees = models.ManyToManyField(
        'custom_auth.Artist',
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
    # Collaborators field is defined above
    likes = models.ManyToManyField('custom_auth.User', related_name='liked_gigs', blank=True)
    
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

    def clean(self):
        """
        Validate the model before saving.
        Ensures ticket price meets the minimum requirements for artist-hosted shows.
        """
        if self.gig_type == self.GigType.ARTIST_GIG and self.ticket_price is not None:
            # Get the creator's performance tier (default to FRESH_TALENT if not set)
            creator_tier = PerformanceTier.FRESH_TALENT
            if hasattr(self.created_by, 'artist') and self.created_by.artist:
                creator_tier = self.created_by.artist.performance_tier
            
            # Validate the ticket price
            validation = validate_ticket_price(creator_tier, self.ticket_price)
            if not validation['is_valid']:
                raise PricingValidationError(validation['message'])
    
    def requires_price_confirmation(self, price=None):
        """
        Check if the given price requires confirmation based on the artist's tier.
        
        Args:
            price (Decimal, optional): Price to check. Uses self.ticket_price if None.
            
        Returns:
            dict: {
                'requires_confirmation': bool,
                'message': str,  # Explanation if confirmation is needed
                'suggested_range': str  # Suggested price range if applicable
            }
        """
        if price is None:
            price = self.ticket_price
            
        if price is None:
            return {
                'requires_confirmation': False,
                'message': '',
                'suggested_range': ''
            }
            
        # Get the creator's performance tier (default to FRESH_TALENT if not set)
        creator_tier = PerformanceTier.FRESH_TALENT
        if hasattr(self.created_by, 'artist') and self.created_by.artist:
            creator_tier = self.created_by.artist.performance_tier
            
        # Minimum price check
        price = float(price)
        if price < 5:
            return {
                'requires_confirmation': True,
                'message': 'Minimum ticket price is $5 for all artist-hosted shows.',
                'suggested_range': '$5+'
            }
            
        # Tier-specific guardrails (only for first three tiers)
        tier_ranges = {
            PerformanceTier.FRESH_TALENT: (5, 10),
            PerformanceTier.NEW_BLOOD: (5, 30),
            PerformanceTier.UP_AND_COMING: (7, 35)
        }
        
        if creator_tier in tier_ranges:
            min_price, max_price = tier_ranges[creator_tier]
            if price < min_price or price > max_price:
                tier_name = creator_tier.label
                return {
                    'requires_confirmation': True,
                    'message': f'For {tier_name}, the suggested ticket price range is ${min_price} - ${max_price}.',
                    'suggested_range': f'${min_price} - ${max_price}'
                }
        
        return {
            'requires_confirmation': False,
            'message': '',
            'suggested_range': ''
        }
    
    def save(self, *args, **kwargs):
        # Set expires_at to 10 minutes after created_at if not already set
        if not self.expires_at and self.created_at:
            self.expires_at = self.created_at + timezone.timedelta(minutes=10)
            
        # Run model validation
        self.full_clean()
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
    
