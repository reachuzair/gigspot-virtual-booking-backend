from django.db import models
from django.core.validators import MinValueValidator
from custom_auth.models import Artist, Venue, User, PerformanceTier
from django.utils import timezone
from django.core.exceptions import ValidationError
from .utils import validate_ticket_price, PricingValidationError
import os
import logging

logger = logging.getLogger(__name__)


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
    ARTIST_GIG = 'artist_gig', 'Artist Gig'  # Created by artist using "Create a Show"
    VENUE_GIG = 'venue_gig', 'Venue Gig'     # Created by venue
    TOUR_GIG = 'tour_gig', 'Tour Gig'        # Part of a tour (artist-created multi-city)


class TourStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PLANNING = 'planning', 'Planning'
    ANNOUNCED = 'announced', 'Announced'
    IN_PROGRESS = 'in_progress', 'In Progress'
    COMPLETED = 'completed', 'Completed'
    CANCELLED = 'cancelled', 'Cancelled'


class VehicleType(models.TextChoices):
    CAR = 'car', 'Car'
    VAN = 'van', 'Van'
    BUS = 'bus', 'Bus'
    FLIGHT = 'flight', 'Flight'
    TRAIN = 'train', 'Train'
    OTHER = 'other', 'Other'


class Tour(models.Model):
    """Model for managing multi-city tours"""
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255, help_text='Name of the tour',null=True, blank=True)
    
    # Tour planning fields
    vehicle_type = models.CharField(
        max_length=20,
        choices=VehicleType.choices,
        default=VehicleType.CAR,
        help_text='Type of vehicle for travel between cities'
    )
    driving_range_km = models.PositiveIntegerField(
        default=100,
        help_text='Maximum driving distance in kilometers between tour stops',
        validators=[MinValueValidator(1)]
    )
    selected_states = models.JSONField(
        default=list,
        help_text='List of state names selected for the tour'
    )
    selected_cities = models.JSONField(
        default=list,
        help_text='List of city names selected for the tour'
    )
    description = models.TextField(blank=True, null=True)
    artist = models.ForeignKey(
        Artist,
        on_delete=models.CASCADE,
        related_name='tours',
        help_text='The artist/band going on tour'
    )
    start_date = models.DateField(help_text='Tour start date',null=True, blank=True)
    end_date = models.DateField(help_text='Tour end date',null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=TourStatus.choices,
        default=TourStatus.DRAFT,
        help_text='Current status of the tour'
    )
    is_featured = models.BooleanField(
        default=False,
        help_text='Whether this tour is featured on the platform'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-start_date', 'title']
        verbose_name = 'Tour'
        verbose_name_plural = 'Tours'

    def __str__(self):
        return f"{self.title} - {self.artist.user.name} ({self.start_date.year})"
    
    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({
                'end_date': 'End date must be after start date.'
            })
    
    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
    
    @property
    def gigs_count(self):
        """Return the number of gigs in this tour"""
        return self.gigs.count()
    
    @property
    def cities(self):
        """Return a list of unique cities in this tour"""
        from django.db.models import F
        return list(set(
            self.gigs.filter(venue__isnull=False)
                   .exclude(venue__address__isnull=True)
                   .exclude(venue__address__exact='')
                   .annotate(city=models.functions.Substr(
                       'venue__address',
                       1,
                       models.functions.StrIndex('venue__address', models.Value(',')) - 1
                   ))
                   .values_list('city', flat=True)
        ))
    
    @property
    def is_active(self):
        """Check if the tour is currently active"""
        today = timezone.now().date()
        return self.start_date <= today <= self.end_date and self.status == TourStatus.ANNOUNCED


class Gig(models.Model):
    """Model for individual gigs/shows, which can be standalone or part of a tour"""
    id = models.AutoField(primary_key=True)
    
    # Gig type and basic info
    gig_type = models.CharField(

        max_length=20,
        choices=GigType.choices,
        default=GigType.ARTIST_GIG,
        help_text='Type of gig (artist-created, venue-created, or part of a tour)'
    )
    
    # Tour related fields
    is_part_of_tour = models.BooleanField(
        default=False,
        help_text='Whether this gig is part of a tour',
        db_index=True
    )
    tour = models.ForeignKey(
        Tour,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='gigs',
        help_text='The tour this gig belongs to, if any'
    )
    tour_order = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='The order of this gig in the tour sequence',
        db_index=True
    )
    

    # Core fields
    title = models.CharField(
        max_length=255, help_text='Title of the gig/event', default="", blank=True)
    description = models.TextField(blank=True, null=True, default="")
    event_date = models.DateTimeField(default=timezone.now)
    booking_start_date = models.DateTimeField(null=True, blank=True)
    booking_end_date = models.DateTimeField(null=True, blank=True)

    # Media
    flyer_image = models.ImageField(
        upload_to=event_flyer_path, blank=True, null=True)

    # Relationships
    created_by = models.ForeignKey(User, on_delete=models.CASCADE,
                                   related_name='created_gigs', default=None, null=True, blank=True)
    venue = models.ForeignKey(
        Venue, on_delete=models.CASCADE, related_name='gigs', null=True, blank=True)
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
    genre = models.CharField(
        max_length=20,
        choices=GenreChoices.choices,
        default=GenreChoices.RAP,
        help_text='Genre of the gig',
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
        default=5.0,
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
    likes = models.ManyToManyField(
        'custom_auth.User', related_name='liked_gigs', blank=True)

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

    from .models import GigType  # Ensure this is imported at the top

    def clean(self):
        """
        Validate the model before saving.
        Ensures ticket price meets the minimum requirements for artist-hosted shows.
        """

        if self.gig_type == GigType.ARTIST_GIG and self.ticket_price is not None:
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
    venue = models.ForeignKey(Venue, on_delete=models.CASCADE,
                              related_name='contracts', default=None, null=True, blank=True)
    venue_signed = models.BooleanField(default=False)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE,
                               related_name='contracts', default=None, null=True, blank=True)
    artist_signed = models.BooleanField(default=False)
    pdf = models.FileField(upload_to='gigs/contracts/', blank=True, null=True)
    image = models.ImageField(
        upload_to='gigs/contracts/', blank=True, null=True)
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
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='gig_invites_sent', default=None, null=True, blank=True)
    artist_received = models.ForeignKey(
        Artist, on_delete=models.CASCADE, related_name='gig_invites_received')
    status = models.CharField(
        max_length=255, choices=GigInviteStatus.choices, default=GigInviteStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    
class VehicleType(models.TextChoices):
    """Types of vehicles that can be used for tour travel"""
    CAR = 'car', 'Car'
    VAN = 'van', 'Van'
    BUS = 'bus', 'Bus'
    FLIGHT = 'flight', 'Flight'
    TRAIN = 'train', 'Train'
    OTHER = 'other', 'Other'


class TourVenueSuggestion(models.Model):
    """Model for storing venue suggestions for tour stops"""
    tour = models.ForeignKey(
        Tour,
        on_delete=models.CASCADE,
        related_name='suggested_venues',
        help_text='The tour this suggestion is for'
    )
    venue = models.ForeignKey(
        Venue,
        on_delete=models.CASCADE,
        related_name='tour_suggestions',
        help_text='The suggested venue'
    )
    event_date = models.DateField(
        help_text='Scheduled date for the show at this venue',
        default=timezone.now
    )
    is_booked = models.BooleanField(
        default=False,
        help_text='Whether this venue has been booked for the tour'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['tour', 'event_date']
        unique_together = ['tour', 'venue']
        verbose_name = 'Tour Venue Suggestion'
        verbose_name_plural = 'Tour Venue Suggestions'

    def __str__(self):
        return f"{self.venue.name} for {self.tour.title} on {self.event_date}"
    
    @classmethod
    def get_booked_venues(cls, tour_id):
        """Get all booked venues for a tour, ordered by event date"""
        return cls.objects.filter(
            tour_id=tour_id,
            is_booked=True
        ).select_related('venue').order_by('event_date')

