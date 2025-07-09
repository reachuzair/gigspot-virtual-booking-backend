from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from datetime import datetime, date, timedelta
from django.utils.text import slugify
from django.db.models import F, ExpressionWrapper, FloatField, Sum
from django.utils.functional import cached_property
from model_utils import FieldTracker
from decimal import Decimal, ROUND_HALF_UP
import random
import logging
from django.core.cache import cache

from subscriptions.models import SubscriptionPlan

logger = logging.getLogger(__name__)


class ArtistMonthlyMetrics(models.Model):
    """
    Tracks monthly metrics for artists, storing only the essential percentage metrics needed for analytics.
    """
    artist = models.ForeignKey(
        'Artist',
        on_delete=models.CASCADE,
        related_name='monthly_metrics'
    )
    month = models.DateField(
        help_text="First day of the month these metrics represent"
    )
    
    # Core Percentage Metrics (0-100 scale)
    fan_engagement_pct = models.FloatField(
        default=0.0,
        help_text="Fan engagement as a percentage (0-100)"
    )
    social_following_pct = models.FloatField(
        default=0.0,
        help_text="Social media following as a percentage of max possible (0-100)"
    )
    playlist_views_pct = models.FloatField(
        default=0.0,
        help_text="Playlist views as a percentage of max possible (0-100)"
    )
    buzz_score_pct = models.FloatField(
        default=0.0,
        help_text="Buzz score as a percentage (0-100)"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name_plural = "Artist Monthly Metrics"
        unique_together = ('artist', 'month')
        ordering = ['-month']
        indexes = [
            models.Index(fields=['month']),
            models.Index(fields=['artist', 'month']),
        ]
    
    def __str__(self):
        return f"{self.artist} - {self.month.strftime('%B %Y')}"
    
    def calculate_fan_engagement(self):
        """Calculate fan engagement rate based on streams and monthly listeners."""
        if self.monthly_listeners > 0:
            engagement = (Decimal(self.streams) / self.monthly_listeners) * 100
            return engagement.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')
    
    def calculate_social_growth(self, previous_month):
        """Calculate social media growth rate compared to previous month."""
        if not previous_month:
            return Decimal('0.00')
            
        current_total = sum([
            self.instagram_followers,
            self.tiktok_followers,
            self.spotify_followers,
            self.youtube_subscribers
        ])
        
        previous_total = sum([
            previous_month.instagram_followers,
            previous_month.tiktok_followers,
            previous_month.spotify_followers,
            previous_month.youtube_subscribers
        ])
        
        if previous_total > 0:
            growth = ((current_total - previous_total) / previous_total) * 100
            return Decimal(str(growth)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')
    
    def save(self, *args, **kwargs):
        # Ensure month is set to the first day of the month
        if isinstance(self.month, (datetime, date)):
            self.month = self.month.replace(day=1)
        
        # Calculate metrics if not set
        if not self.pk or 'fan_engagement_rate' not in kwargs.get('update_fields', []):
            self.fan_engagement_rate = self.calculate_fan_engagement()
            
            # Calculate social growth if we have a previous month
            if not self.pk:  # Only on create
                prev_month = self.month - timedelta(days=1)
                prev_month = prev_month.replace(day=1)
                try:
                    prev_metrics = ArtistMonthlyMetrics.objects.get(
                        artist=self.artist,
                        month=prev_month
                    )
                    self.social_growth_rate = self.calculate_social_growth(prev_metrics)
                except ArtistMonthlyMetrics.DoesNotExist:
                    self.social_growth_rate = Decimal('0.00')
        
        super().save(*args, **kwargs)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class ROLE_CHOICES(models.TextChoices):
    ARTIST = 'artist', 'Artist'
    VENUE = 'venue', 'Venue'
    FAN = 'fan', 'Fan'


def user_profile_image_path(instance, filename):
    # Generate a unique filename using name and timestamp
    import time
    timestamp = int(time.time())
    extension = filename.split('.')[-1].lower()
    new_filename = f"{slugify(instance.name)}_{timestamp}.{extension}"
    return f'profile_images/{new_filename}'


class User(AbstractBaseUser, PermissionsMixin):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255, default="")
    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=255, choices=ROLE_CHOICES.choices, default=ROLE_CHOICES.FAN)
    profileCompleted = models.BooleanField(default=False)
    profileImage = models.ImageField(
        upload_to=user_profile_image_path, blank=True, null=True, default=None)
    ver_code = models.CharField(max_length=255, blank=True, null=True)
    ver_code_expires = models.DateTimeField(blank=True, null=True)
    email_verified = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)  # Required for Django admin
    is_active = models.BooleanField(default=True)  # Required for Django admin
    contract_pin = models.CharField(
        max_length=255, blank=True, null=True, default="")
    contract_pin_expires_in = models.DateTimeField(
        blank=True, null=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'  # Use email as the unique identifier for authentication
    # Fields required when creating a user via createsuperuser
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    def gen_otp(self):
        """Generate a 6-digit numeric OTP and save it with an expiry date."""
        otp = random.randint(
            100000, 999999)  # Generate a random number between 100000 and 999999
        self.ver_code = otp  # Save OTP to ver_code field
        # Set expiry to 60 minutes from now
        self.ver_code_expires = timezone.now() + timedelta(minutes=60)
        self.save()  # Save the user instance to persist changes
        return otp

    def gen_contract_pin(self):
        """Generate a 6-digit numeric Contract Pin and save it with an expiry date."""
        contract_pin = random.randint(
            100000, 999999)  # Generate a random number between 100000 and 999999
        self.contract_pin = contract_pin  # Save OTP to contract_pin field
        # Set expiry to 60 minutes from now
        self.contract_pin_expires_in = timezone.now() + timedelta(minutes=60)
        self.save()  # Save the user instance to persist changes
        return contract_pin


class _TierConfig:
    """
    Internal class to hold tier configuration data.
    This is separate from the enum to avoid enum instantiation issues.
    """
    # Artist tier configuration
    # Format: (min_followers, max_followers, min_monthly_listeners, max_monthly_listeners,
    #          min_streams, max_streams, min_venue_capacity, max_venue_capacity, venue_types)
    ARTIST_TIERS = {
        'FRESH_TALENT': (
            0, 1000,  # Followers
            0, 1000,  # Monthly listeners
            0, 100_000,  # Total streams
            0, 100,  # Venue capacity
            'Small coffee shops, bars, open mic nights, art spaces'
        ),
        'NEW_BLOOD': (
            1000, 10000,
            1000, 10000,
            0, 100_000,
            50, 300,
            'Small music venues, community theaters, bars with dedicated stages'
        ),
        'UP_AND_COMING': (
            10000, 50000,
            10000, 50000,
            100_000, 1_000_000,
            200, 800,
            'Independent venues, mid-size clubs, college venues'
        ),
        'RISING_STAR': (
            50000, 200000,
            50000, 200000,
            1_000_000, 2_000_000,
            500, 1000,
            'Larger clubs, music halls, local amphitheaters'
        ),
        'SCENE_KING': (
            200000, 500000,
            200000, 500000,
            2_000_000, 10_000_000,
            1000, 3000,
            'Regional theaters, large concert halls, premier venues'
        ),
        'ROCKSTAR': (
            500000, 2000000,
            500000, 2000000,
            10_000_000, 50_000_000,
            3000, 10000,
            'Large music halls, major theaters, festival stages'
        ),
        'GOLIATH': (
            2000000, None,  # No upper limit
            2000000, None,
            50_000_000, None,
            10000, None,  # No upper capacity limit
            'Stadiums, arenas, national amphitheaters, headlining festival slots'
        )
    }
    
    # Venue tier configuration
    # Format: (min_capacity, max_capacity)
    VENUE_TIERS = {
        'VENUE_1': (0, 50, 'Small Venue (0-50)'),
        'VENUE_2': (50, 100, 'Small Club (50-100)'),
        'VENUE_3': (100, 200, 'Club (100-200)'),
        'VENUE_4': (200, 400, 'Large Club (200-400)'),
        'VENUE_5': (400, 800, 'Theater (400-800)'),
        'VENUE_6': (800, 1500, 'Concert Hall (800-1500)'),
        'VENUE_7': (1500, None, 'Arena (1500+)')
    }
    
    # Map artist tiers to their eligible venue tier names
    # These should match the tier names in the VenueTier model
    ARTIST_VENUE_MAPPING = {
        'FRESH_TALENT': ['CLASS_IA'],
        'NEW_BLOOD': ['CLASS_IA', 'CLASS_IIA'],
        'UP_AND_COMING': ['CLASS_IIA', 'CLASS_IIIA'],
        'RISING_STAR': ['CLASS_IIIA', 'CLASS_IVA'],
        'SCENE_KING': ['CLASS_IVA', 'CLASS_VA'],
        'ROCKSTAR': ['CLASS_VA', 'CLASS_VIA'],
        'GOLIATH': ['CLASS_VIA']
    }

    @classmethod
    def get_artist_config(cls, tier_name):
        """Get configuration for a specific artist tier"""
        return cls.ARTIST_TIERS.get(tier_name)
        
    @classmethod
    def get_venue_config(cls, tier_name):
        """Get configuration for a specific venue tier"""
        return cls.VENUE_TIERS.get(tier_name)
        
    @classmethod
    def get_venue_tier_for_capacity(cls, capacity):
        """Get the appropriate venue tier for a given capacity"""
        if capacity is None:
            return None
            
        for tier_name, (min_cap, max_cap, _) in cls.VENUE_TIERS.items():
            if (min_cap is None or capacity >= min_cap) and \
               (max_cap is None or capacity <= max_cap):
                return tier_name
        return None


class PerformanceTier(models.TextChoices):
    """
    Defines artist performance tiers with detailed metrics and venue matching capabilities.
    Each tier is defined with follower count ranges, monthly listeners, total streams,
    and matching venue capacity ranges.
    """
    # Define the enum values
    FRESH_TALENT = 'fresh_talent', 'Fresh Talent (0-1k)'
    NEW_BLOOD = 'new_blood', 'New Blood (1k-10k)'
    UP_AND_COMING = 'up_and_coming', 'Up and Coming (10k-50k)'
    RISING_STAR = 'rising_star', 'Rising Star (50k-200k)'
    SCENE_KING = 'scene_king', 'Scene King (200k-500k)'
    ROCKSTAR = 'rockstar', 'Rockstar (500k-2M)'
    GOLIATH = 'goliath', 'Goliath (2M+)'
    


    @classmethod
    def get_tier_by_metrics(cls, follower_count=None, monthly_listeners=None, total_streams=None):
        """
        Determine the appropriate artist tier based on any combination of metrics.
        Uses the most specific match available.
        """
        # If we have all metrics, find the most specific match
        if all([follower_count is not None, monthly_listeners is not None, total_streams is not None]):
            for tier_name in _TierConfig.ARTIST_TIERS:
                config = _TierConfig.get_artist_config(tier_name)
                if not config:
                    continue
                    
                min_fol, max_fol, min_ml, max_ml, min_str, max_str, _, _, _ = config
                
                # Check if all metrics fall within the tier's range
                if ((min_fol is None or follower_count >= min_fol) and 
                    (max_fol is None or follower_count <= max_fol) and
                    (min_ml is None or (monthly_listeners is not None and monthly_listeners >= min_ml)) and
                    (max_ml is None or (monthly_listeners is not None and monthly_listeners <= max_ml)) and
                    (min_str is None or (total_streams is not None and total_streams >= min_str)) and
                    (max_str is None or (total_streams is not None and total_streams <= max_str))):
                    return cls[tier_name]
        
        # Fall back to follower count if other metrics aren't available
        if follower_count is not None:
            return cls.get_artist_tier(follower_count)
            
        # If no metrics are provided, return the lowest tier
        return cls.FRESH_TALENT

    @classmethod
    def get_artist_tier(cls, follower_count):
        """Get artist tier based on follower count"""
        if follower_count is None:
            return cls.FRESH_TALENT
            
        for tier_name in _TierConfig.ARTIST_TIERS:
            config = _TierConfig.get_artist_config(tier_name)
            if not config:
                continue
                
            min_fol, max_fol, _, _, _, _, _, _, _ = config
            if (min_fol is None or follower_count >= min_fol) and \
               (max_fol is None or follower_count <= max_fol):
                return cls[tier_name]
                
        return cls.FRESH_TALENT
    
    @classmethod
    def get_venue_tier(cls, capacity):
        """
        Get the appropriate venue tier name for a given capacity.
        Returns a string representing the venue tier name.
        """
        return _TierConfig.get_venue_tier_for_capacity(capacity)
    
    @classmethod
    def get_eligible_venue_tiers(cls, artist_tier):
        """
        Get all venue tiers that are suitable for an artist tier
        Returns a list of VenueTier objects
        """
        if not artist_tier or artist_tier not in cls:
            return VenueTier.objects.none()
            
        # Get eligible venue tier names for this artist tier
        eligible_venue_tier_names = _TierConfig.ARTIST_VENUE_MAPPING.get(artist_tier.name, [])
        if not eligible_venue_tier_names:
            return VenueTier.objects.none()
            
        # Get the corresponding VenueTier objects
        return VenueTier.objects.filter(tier__in=eligible_venue_tier_names).order_by('min_capacity')
    
    @classmethod
    def get_venue_capacity_range(cls, artist_tier):
        """Get the recommended venue capacity range for an artist tier"""
        if not artist_tier or artist_tier not in cls:
            return None, None
            
        config = _TierConfig.get_artist_config(artist_tier.name)
        if config:
            return config[6], config[7]  # min_venue_capacity, max_venue_capacity
        return None, None
    
    @classmethod
    def get_venue_examples(cls, artist_tier):
        """Get example venues for an artist tier"""
        if not artist_tier or artist_tier not in cls:
            return ""
            
        config = _TierConfig.get_artist_config(artist_tier.name)
        if config:
            return config[8]  # example_venues
        return ""
    
    @classmethod
    def get_tier_for_followers(cls, follower_count):
        """Alias for backward compatibility"""
        return cls.get_artist_tier(follower_count)
    
    @property
    def min_followers(self):
        """Get minimum followers for this tier"""
        config = _TierConfig.get_artist_config(self.name)
        return config[0] if config else 0
    
    @property
    def max_followers(self):
        """Get maximum followers for this tier"""
        config = _TierConfig.get_artist_config(self.name)
        return config[1] if config else None
    
    @property
    def min_venue_capacity(self):
        """Get minimum recommended venue capacity for this tier"""
        config = _TierConfig.get_artist_config(self.name)
        return config[6] if config else 0
    
    @property
    def max_venue_capacity(self):
        """Get maximum recommended venue capacity for this tier"""
        config = _TierConfig.get_artist_config(self.name)
        return config[7] if config else None
    
    @property
    def example_venues(self):
        """Get example venues for this tier"""
        config = _TierConfig.get_artist_config(self.name)
        return config[8] if config else ""


class VenueTier(models.Model):
    """
    Represents different tiers of venues based on capacity and the artist tiers they can host.
    """
    class TierClass(models.TextChoices):
        CLASS_IA = 'CLASS_IA', 'Class I-A (Small Local Venues)'
        CLASS_IIA = 'CLASS_IIA', 'Class II-A (Mid-Sized Growth Venues)'
        CLASS_IIIA = 'CLASS_IIIA', 'Class III-A (Regional Venues)'
        CLASS_IVA = 'CLASS_IVA', 'Class IV-A (Major Music Halls & Theaters)'
        CLASS_VA = 'CLASS_VA', 'Class V-A (Premier National Venues)'
        CLASS_VIA = 'CLASS_VIA', 'Class VI-A (Stadiums & Arenas)'
    
    # Tier configuration with (min_capacity, max_capacity, eligible_artist_tiers, example_venues)
    TIER_CONFIG = {
        TierClass.CLASS_IA: (
            50, 300,
            ['FRESH_TALENT', 'NEW_BLOOD'],
            'Small bars, lounges, intimate stages'
        ),
        TierClass.CLASS_IIA: (
            200, 800,
            ['NEW_BLOOD', 'UP_AND_COMING'],
            'Independent clubs, small theaters, college venues'
        ),
        TierClass.CLASS_IIIA: (
            500, 1500,
            ['UP_AND_COMING', 'RISING_STAR'],
            'Larger music halls, mid-sized theaters'
        ),
        TierClass.CLASS_IVA: (
            1000, 3000,
            ['RISING_STAR', 'SCENE_KING'],
            'Large theaters, concert halls, regional amphitheaters'
        ),
        TierClass.CLASS_VA: (
            3000, 10000,
            ['SCENE_KING', 'ROCKSTAR'],
            'Large concert venues, festival main stages'
        ),
        TierClass.CLASS_VIA: (
            10000, 100000,  # Upper limit set to 100k as a reasonable max
            ['ROCKSTAR', 'GOLIATH'],
            'Arenas, stadiums, festival headliner slots'
        )
    }
    
    tier = models.CharField(
        max_length=20,
        choices=TierClass.choices,
        unique=True,
        help_text="The classification tier of the venue"
    )
    min_capacity = models.PositiveIntegerField(
        help_text="Minimum capacity for this venue tier"
    )
    max_capacity = models.PositiveIntegerField(
        help_text="Maximum capacity for this venue tier"
    )
    eligible_artist_tiers = models.JSONField(
        help_text="List of artist tiers that can perform at this venue",
        default=list
    )
    description = models.TextField(
        blank=True,
        help_text="Description of the venue tier"
    )
    example_venues = models.TextField(
        help_text="Example venues that fall into this tier"
    )
    
    class Meta:
        ordering = ['min_capacity']
        verbose_name = 'Venue Tier'
        verbose_name_plural = 'Venue Tiers'
    
    def __str__(self):
        return self.get_tier_display()
    
    def save(self, *args, **kwargs):
        """Auto-populate fields based on tier configuration."""
        if self.tier and self.tier in self.TIER_CONFIG:
            config = self.TIER_CONFIG[self.tier]
            self.min_capacity = config[0]
            self.max_capacity = config[1]
            self.eligible_artist_tiers = config[2]
            self.example_venues = config[3]
        super().save(*args, **kwargs)
    
    @classmethod
    def initialize_tiers(cls):
        """Initialize or update all venue tiers based on configuration."""
        for tier_value, tier_display in cls.TierClass.choices:
            cls.objects.update_or_create(
                tier=tier_value,
                defaults={
                    'min_capacity': cls.TIER_CONFIG[tier_value][0],
                    'max_capacity': cls.TIER_CONFIG[tier_value][1],
                    'eligible_artist_tiers': cls.TIER_CONFIG[tier_value][2],
                    'example_venues': cls.TIER_CONFIG[tier_value][3],
                }
            )
    
    @classmethod
    def get_eligible_venues_for_artist_tier(cls, artist_tier):
        """
        Get all venue tiers that are eligible for a specific artist tier.
        
        Args:
            artist_tier (str): The artist's performance tier
            
        Returns:
            QuerySet: Venue tiers that can host the artist
        """
        return cls.objects.filter(
            eligible_artist_tiers__contains=[artist_tier]
        )
    
    @classmethod
    def get_tier_for_capacity(cls, capacity):
        """
        Get the appropriate venue tier based on capacity.
        
        Args:
            capacity (int): The venue's capacity
            
        Returns:
            VenueTier: The matching venue tier, or None if no match
        """
        try:
            capacity = int(capacity)
            return cls.objects.get(
                min_capacity__lte=capacity,
                max_capacity__gte=capacity
            )
        except (ValueError, cls.DoesNotExist):
            return None





class ArtistManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().select_related('user')
    
    def with_metrics_updated(self, force_update=False):
        """
        Returns a queryset where each artist's metrics are updated if needed
        """
        from .utils import update_artist_metrics_if_needed
        
        queryset = self.get_queryset()
        for artist in queryset.filter(soundcharts_uuid__isnull=False):
            update_artist_metrics_if_needed(artist, force_update=force_update)
        return queryset


class Artist(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE,
        related_name='artist_profile',
        help_text="The user account associated with this artist"
    )
    full_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Artist's full legal name"
    )
    phone_number = models.CharField(
        max_length=20, 
        blank=True, 
        null=True,
        help_text="Contact phone number with country code"
    )
    verification_docs = models.FileField(
        upload_to='artist_verification_docs', 
        blank=True, 
        null=True,
        help_text="Upload any verification documents required"
    )
    likes = models.ManyToManyField(User, related_name='liked_artists', blank=True)
    logo = models.ImageField(
        upload_to='artist_logo', 
        blank=True, 
        null=True,
        help_text="Artist's profile image/logo"
    )
    band_name = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Stage name or band name"
    )
    band_email = models.EmailField(
        blank=True, 
        null=True,
        help_text="Professional email for booking inquiries"
    )
    city = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Base city of the artist"
    )
    state = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="State/Region of the artist"
    )
    performance_tier = models.CharField(
        max_length=50,
        choices=PerformanceTier.choices, 
        default=PerformanceTier.FRESH_TALENT,
        help_text="Artist's performance tier based on follower count"
    )
    subscription_tier = models.CharField(
        max_length=50,
        choices=SubscriptionPlan.TIER_CHOICES,
        default='FREE',
        help_text="Subscription level for premium features"
    )
    shows_created = models.PositiveIntegerField(
        default=0,
        help_text="Number of shows created by this artist"
    )
    active_collaborations = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='collaborators',
        blank=True,
        help_text="Other artists this artist is collaborating with"
    )
    soundcharts_uuid = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        default=None, 
        unique=True,
        help_text='SoundCharts artist UUID for fetching tier information'
    )
    monthly_listeners = models.PositiveIntegerField(
        default=0,
        help_text="Number of monthly listeners on streaming platforms"
    )
    streams = models.BigIntegerField(
        default=0,
        help_text="Total number of streams across all platforms"
    )
    # Social media followers
    instagram_followers = models.PositiveIntegerField(
        default=0,
        help_text="Number of Instagram followers"
    )
    tiktok_followers = models.PositiveIntegerField(
        default=0,
        help_text="Number of TikTok followers"
    )
    spotify_followers = models.PositiveIntegerField(
        default=0,
        help_text="Number of Spotify followers"
    )
    youtube_subscribers = models.PositiveIntegerField(
        default=0,
        help_text="Number of YouTube subscribers"
    )
    # Analytics fields
    playlist_views = models.PositiveIntegerField(
        default=0,
        help_text="Total number of playlist views"
    )
    # Engagement and buzz metrics as percentages (0-100)
    fan_engagement_pct = models.FloatField(
        default=0.0,
        help_text="Fan engagement as a percentage (0-100)"
    )
    buzz_score_pct = models.FloatField(
        default=0.0,
        help_text="Buzz score as a percentage (0-100)"
    )
    social_following_pct = models.FloatField(
        default=0.0,
        help_text="Social media following as a percentage of max possible (0-100)"
    )
    playlist_views_pct = models.FloatField(
        default=0.0,
        help_text="Playlist views as a percentage of max possible (0-100)"
    )
    onFireStatus = models.BooleanField(
        default=False,
        help_text="Whether the artist is currently trending"
    )
    last_metrics_update = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the metrics were last updated"
    )
    connections = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        related_name='artist_connections',
        blank=True,
        help_text="Network connections with other artists/industry"
    )
    stripe_account_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        default=None,
        help_text="Stripe Connect account ID for payments"
    )
    stripe_onboarding_completed = models.BooleanField(
        default=False,
        help_text="Whether Stripe onboarding is completed"
    )
    last_tier_update = models.DateTimeField(
        null=True, 
        blank=True, 
        help_text='When the tier was last updated from SoundCharts'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    objects = ArtistManager()
    
    # Track changes to metrics fields
    metrics_tracker = FieldTracker(fields=[
        'instagram_followers',
        'tiktok_followers',
        'spotify_followers',
        'youtube_subscribers',
        'playlist_views',
        'fan_engagement_pct',
        'buzz_score_pct',
        'onFireStatus',
        'monthly_listeners',
        'streams',
        'social_following_pct',
        'playlist_views_pct'
    ])

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Artist'
        verbose_name_plural = 'Artists'
        indexes = [
            models.Index(fields=['performance_tier']),
            models.Index(fields=['subscription_tier']),
            models.Index(fields=['buzz_score_pct']),
        ]

    def __str__(self):
        return f"{self.display_name} - {self.get_performance_tier_display()}"
        
    @property
    def display_name(self):
        """Get the display name (band name or user name)"""
        return self.band_name or self.user.name

    def update_metrics_from_soundcharts(self, force_update=False):
        """
        Update artist metrics using SoundCharts API and calculate buzz score
        
        Args:
            force_update (bool): If True, force update even if recently updated
            
        Returns:
            dict: Result of the update with status and data
        """
        print(f"[DEBUG] Starting update_metrics_from_soundcharts for artist {self.id} (UUID: {self.soundcharts_uuid})")
        
        # Initialize SoundCharts API client
        from services.soundcharts import SoundChartsAPI
        soundcharts = SoundChartsAPI()
        
        # If we don't have a UUID, try to find the artist by  full name
        if not self.soundcharts_uuid:
            artist_name = self.full_name or (self.user.full_name if hasattr(self.user, 'full_name') and self.user.full_name else None)
            if not artist_name:
                return {
                    'success': False,
                    'message': 'No artist name available for search. Please set a band name or full name.',
                    'code': 'missing_name'
                }
                
            print(f"[DEBUG] No SoundCharts UUID found, searching for artist by name: {artist_name}")
            search_result = soundcharts.search_artist_by_name(artist_name)
            
            if 'uuid' in search_result:
                self.soundcharts_uuid = search_result['uuid']
                self.save(update_fields=['soundcharts_uuid', 'updated_at'])
                print(f"[DEBUG] Found SoundCharts UUID: {self.soundcharts_uuid}")
            else:
                print(f"[WARNING] Could not find artist on SoundCharts: {search_result.get('error', 'Unknown error')}")
                return {
                    'success': False,
                    'message': f"Could not find artist on SoundCharts: {search_result.get('error', 'Unknown error')}",
                    'code': 'artist_not_found'
                }
            
        # Check if we have a UUID now
        if not self.soundcharts_uuid:
            print("[ERROR] No SoundCharts UUID available after search")
            return {
                'success': False,
                'message': 'No SoundCharts UUID available',
                'code': 'missing_uuid'
            }
            
        # Check if we recently updated (within 24 hours)
        if not force_update and self.last_metrics_update:
            time_since_update = timezone.now() - self.last_metrics_update
            if time_since_update.total_seconds() < 24 * 60 * 60:  # 24 hours
                print("[DEBUG] Metrics updated recently, skipping")
                return {
                    'success': True,
                    'message': 'Metrics updated recently',
                    'code': 'recently_updated'
                }
            
        try:
            from services.soundcharts import SoundChartsAPI
            
            # Initialize API client
            print("[DEBUG] Initializing SoundCharts API client")
            api = SoundChartsAPI()
            
            # Get artist metrics including buzz score
            print(f"[DEBUG] Fetching metrics for UUID: {self.soundcharts_uuid}")
            result = api.get_artist_buzz_score(self.soundcharts_uuid)
            print(f"[DEBUG] API Response: {result}")
            
            if not result or not result.get('success'):
                error_msg = result.get('error', 'Failed to fetch artist data from SoundCharts')
                logger.error(f"SoundCharts API error: {error_msg}")
                return {
                    'success': False,
                    'message': str(error_msg),
                    'code': 'fetch_failed'
                }
            
            print(f"[DEBUG] Full API response: {result}")
            
            # Check if we got a UUID from the response and update if needed
            related_data = result.get('related', {})
            artist_data = related_data.get('artist', {})
            response_uuid = artist_data.get('uuid')
            
            if response_uuid:
                if response_uuid != self.soundcharts_uuid:
                    print(f"[DEBUG] Updating SoundCharts UUID from {self.soundcharts_uuid} to {response_uuid}")
                    self.soundcharts_uuid = response_uuid
                    # Save the UUID immediately if this is a new one
                    self.save(update_fields=['soundcharts_uuid', 'updated_at'])
                    print("[DEBUG] Saved new SoundCharts UUID to artist record")
            elif not self.soundcharts_uuid:
                print("[WARNING] No SoundCharts UUID found in the API response")
                return {
                    'success': False,
                    'message': 'No SoundCharts UUID found in API response',
                    'code': 'missing_uuid'
                }
            
            # Store original values for change detection
            original_metrics = {
                'monthly_listeners': getattr(self, 'monthly_listeners', 0),
                'instagram_followers': getattr(self, 'instagram_followers', 0),
                'tiktok_followers': getattr(self, 'tiktok_followers', 0),
                'spotify_followers': getattr(self, 'spotify_followers', 0),
                'youtube_subscribers': getattr(self, 'youtube_subscribers', 0),
                'fan_engagement_pct': getattr(self, 'fan_engagement_pct', 0.0),
                'buzz_score_pct': getattr(self, 'buzz_score_pct', 0.0),
                'social_following_pct': getattr(self, 'social_following_pct', 0.0),
                'playlist_views_pct': getattr(self, 'playlist_views_pct', 0.0)
            }
            print(f"[DEBUG] Original metrics: {original_metrics}")
            
            # Get metrics from the API response
            metrics = result.get('metrics', {})
            platform_breakdown = metrics.get('platform_breakdown', {})
            
            # Update platform followers from platform_breakdown
            instagram_data = platform_breakdown.get('instagram', {})
            tiktok_data = platform_breakdown.get('tiktok', {})
            youtube_data = platform_breakdown.get('youtube', {})
            spotify_data = platform_breakdown.get('spotify', {})
            
            # Update platform followers with proper type conversion and defaults
            self.instagram_followers = int(instagram_data.get('followers', 0) or 0)
            self.tiktok_followers = int(tiktok_data.get('followers', 0) or 0)
            self.youtube_subscribers = int(youtube_data.get('followers', 0) or 0)
            self.spotify_followers = int(spotify_data.get('followers', 0) or 0)
            
            # Update monthly listeners (from spotify's monthly_listeners)
            self.monthly_listeners = int(spotify_data.get('monthly_listeners', 0) or 0)
            
            # No longer using _update_buzz_score as we calculate it directly above
            # with the new weighted average formula
            
            print(f"[DEBUG] Updated platform followers - "
                  f"Instagram: {self.instagram_followers}, "
                  f"TikTok: {self.tiktok_followers}, "
                  f"Spotify: {self.spotify_followers}, "
                  f"YouTube: {self.youtube_subscribers}")
            print(f"[DEBUG] Updated monthly_listeners: {self.monthly_listeners}")
            print(f"[DEBUG] Updated buzz_score_pct: {self.buzz_score_pct}")
            
            # Update performance tier based on total followers
            total_followers = int(metrics.get('total_followers', 0))
            self.performance_tier = PerformanceTier.get_artist_tier(total_followers)
            print(f"[DEBUG] Updated performance tier to {self.performance_tier} based on {total_followers} total followers")
            
            # Calculate the four key metrics as percentages
            # 1. Fan Engagement (%)
            # Get engagement rate from metrics if available, otherwise use 0
            metrics = result.get('metrics', {})
            fan_engagement = float(metrics.get('engagement_rate', 0.0)) * 100  # Convert from decimal to percentage
            
            # 2. Social Media Following (% of max possible for tier)
            max_followers_by_tier = {
                PerformanceTier.FRESH_TALENT: 10_000,        # 10K
                PerformanceTier.NEW_BLOOD: 100_000,       # 100K
                PerformanceTier.UP_AND_COMING: 500_000,   # 500K
                PerformanceTier.RISING_STAR: 2_000_000,   # 2M
                PerformanceTier.SCENE_KING: 5_000_000,    # 5M
                PerformanceTier.ROCKSTAR: 20_000_000,     # 20M
                PerformanceTier.GOLIATH: 100_000_000      # 100M
            }
            
            max_possible_followers = max_followers_by_tier.get(self.performance_tier, 10_000_000)  # Default to 10M if tier not found
            social_following_pct = min((total_followers / max_possible_followers) * 100, 100) if max_possible_followers > 0 else 0
            
            # 3. Playlist Views Percentage (Total Playlist Views / Max For Tier) * 100
            playlist_views = result.get('playlist_views', {})
            total_playlist_views = int(playlist_views.get('count', 0) or 0)
            
            # Determine max possible playlist views based on artist tier
            max_playlist_views_by_tier = {
                PerformanceTier.FRESH_TALENT: 100_000,      # 100K
                PerformanceTier.NEW_BLOOD: 500_000,        # 500K
                PerformanceTier.UP_AND_COMING: 1_000_000,  # 1M
                PerformanceTier.RISING_STAR: 5_000_000,    # 5M
                PerformanceTier.SCENE_KING: 10_000_000,    # 10M
                PerformanceTier.ROCKSTAR: 25_000_000,      # 25M
                PerformanceTier.GOLIATH: 100_000_000       # 100M
            }
            
            max_possible_playlist_views = max_playlist_views_by_tier.get(self.performance_tier, 10_000_000)  # Default to 10M if tier not found
            playlist_views_pct = min((total_playlist_views / max_possible_playlist_views) * 100, 100) if max_possible_playlist_views > 0 else 0
            
            # 4. Calculate Buzz Score (weighted average)
            # Weights: Fan Engagement (40%), Social Following (30%), Playlist Views (30%)
            buzz_score_pct = (
                (fan_engagement * 0.4) + 
                (social_following_pct * 0.3) + 
                (playlist_views_pct * 0.3)
            )
            
            # Store the calculated percentages
            self.fan_engagement_pct = fan_engagement
            self.social_following_pct = social_following_pct
            self.playlist_views_pct = playlist_views_pct
            self.buzz_score_pct = buzz_score_pct
            self.playlist_views = total_playlist_views  # Store the raw count as well
            
            # Set onFireStatus based on buzz score (70% or higher)
            on_fire = buzz_score_pct >= 70
            if self.onFireStatus != on_fire:
                self.onFireStatus = on_fire
                changed_fields = changed_fields or []
                changed_fields.append('onFireStatus')
            
            print(f"[DEBUG] Calculated metrics - "
                  f"Fan Engagement: {fan_engagement:.2f}%, "
                  f"Social Following: {social_following_pct:.2f}%, "
                  f"Playlist Views: {playlist_views_pct:.2f}%, "
                  f"Buzz Score: {self.buzz_score_pct:.2f}%")
            
            # Update timestamps
            current_time = timezone.now()
            self.last_metrics_update = current_time
            self.last_tier_update = current_time
            
            # Define fields to update and track changes
            update_fields = [
                'monthly_listeners',
                'instagram_followers',
                'tiktok_followers',
                'spotify_followers',
                'youtube_subscribers',
                'performance_tier',
                'last_metrics_update',
                'last_tier_update',
                'updated_at',
                'fan_engagement_pct',
                'social_following_pct',
                'playlist_views_pct',
                'buzz_score_pct',
                'onFireStatus',
                'playlist_views'
            ]
            
            # Only include fields that actually exist on the model
            update_fields = [f for f in update_fields if hasattr(self, f)]
            print(f"[DEBUG] Fields to check for changes: {update_fields}")
            
            # Track changed fields
            changed_fields = []
            for field in update_fields:
                current_value = getattr(self, field, None)
                if field in original_metrics:
                    old_value = original_metrics[field]
                    # Convert to same type for comparison
                    if isinstance(old_value, float) and isinstance(current_value, (int, float)):
                        old_value = float(old_value)
                        current_value = float(current_value)
                    
                    if current_value != old_value:
                        print(f"[DEBUG] Field changed - {field}: {old_value} ({type(old_value)}) -> {current_value} ({type(current_value)})")
                        changed_fields.append(field)
                    else:
                        print(f"[DEBUG] No change in field: {field} ({current_value} - {type(current_value)})")
            
            # Always update timestamps
            if 'last_metrics_update' not in changed_fields:
                changed_fields.append('last_metrics_update')
            if 'last_tier_update' not in changed_fields:
                changed_fields.append('last_tier_update')
            if 'updated_at' not in changed_fields:
                changed_fields.append('updated_at')
            
            if changed_fields:
                print(f"[DEBUG] Saving changes for fields: {changed_fields}")
                self.save(update_fields=changed_fields)
                logger.info(f"Successfully updated metrics for artist {self.id}: {', '.join(changed_fields)}")
                return {
                    'success': True,
                    'updated': True,
                    'updated_fields': changed_fields,
                    'metrics': metrics,
                    'message': f'Updated {len(changed_fields)} fields for artist {self.id}'
                }
            else:
                logger.info(f"No metric changes detected for artist {self.id}")
                return {
                    'success': True,
                    'updated': False,
                    'message': 'No changes detected',
                    'metrics': metrics
                }

            # Update monthly metrics if any metrics changed
            if hasattr(self, 'get_current_month_metrics') and any(field in changed_fields for field in [
                'monthly_listeners', 'instagram_followers',
                'tiktok_followers', 'spotify_followers', 
                'youtube_subscribers', 'engagement_rate', 'buzz_score'
            ]):
                try:
                    metrics = self.get_current_month_metrics()
                    if metrics:
                        update_data = {}
                        if 'monthly_listeners' in changed_fields:
                            update_data['monthly_listeners'] = self.monthly_listeners
                        if 'instagram_followers' in changed_fields:
                            update_data['instagram_followers'] = self.instagram_followers
                        if 'tiktok_followers' in changed_fields:
                            update_data['tiktok_followers'] = self.tiktok_followers
                        if 'spotify_followers' in changed_fields:
                            update_data['spotify_followers'] = self.spotify_followers
                        if 'youtube_subscribers' in changed_fields:
                            update_data['youtube_subscribers'] = self.youtube_subscribers
                        if 'engagement_rate' in changed_fields:
                            update_data['engagement_rate'] = self.engagement_rate
                        if 'buzz_score' in changed_fields:
                            update_data['buzz_score'] = self.buzz_score
                        
                        if update_data:
                            for key, value in update_data.items():
                                setattr(metrics, key, value)
                            metrics.save()
                            print(f"[DEBUG] Updated monthly metrics for artist {self.id}")
                except Exception as e:
                    logger.error(f"Error updating monthly metrics for artist {self.id}: {str(e)}")
                    print(f"[ERROR] Failed to update monthly metrics: {str(e)}")

            # Calculate and update buzz score if the method exists
            if hasattr(self, '_update_buzz_score'):
                try:
                    monthly_listeners = getattr(self, 'monthly_listeners', 0)
                    streams = getattr(self, 'streams', 0)
                    self._update_buzz_score(monthly_listeners, streams)
                    
                    # Save again if buzz score changed
                    if 'buzz_score' not in changed_fields or 'onFireStatus' not in changed_fields:
                        self.save(update_fields=['buzz_score', 'onFireStatus', 'updated_at'])
                except Exception as e:
                    logger.error(f"Error updating buzz score for artist {getattr(self, 'id', 'unknown')}: {str(e)}")
            
            # Save monthly metrics
            try:
                current_month = timezone.now().replace(day=1).date()
                metrics, created = ArtistMonthlyMetrics.objects.update_or_create(
                    artist=self,
                    month=current_month,
                    defaults={
                        'fan_engagement_pct': self.fan_engagement_pct,
                        'social_following_pct': self.social_following_pct,
                        'playlist_views_pct': self.playlist_views_pct,
                        'buzz_score_pct': self.buzz_score_pct,
                    }
                )
                logger.info(f"Saved monthly metrics for artist {self.id} - {current_month.strftime('%B %Y')}")
            except Exception as e:
                logger.error(f"Error saving monthly metrics for artist {self.id}: {str(e)}", exc_info=True)
            
            # Prepare response data
            response_data = {
                'success': True,
                'message': 'Metrics updated successfully',
                'metrics_updated': len(changed_fields) > 0,
                'buzz_score': self.buzz_score_pct,
                'on_fire': self.onFireStatus,
            }
            
            # Add metrics summary if available
            if hasattr(self, 'get_metrics_summary'):
                try:
                    metrics_summary = self.get_metrics_summary()
                    if metrics_summary:
                        response_data['metrics'] = {
                            'current_month': {
                                'fan_engagement': float(metrics_summary.get('current_month', {}).get('fan_engagement_rate', 0)) if metrics_summary.get('current_month') else 0,
                                'social_following': sum([
                                    metrics_summary['current_month'].get('instagram_followers', 0),
                                    metrics_summary['current_month'].get('tiktok_followers', 0),
                                    metrics_summary['current_month'].get('spotify_followers', 0),
                                    metrics_summary['current_month'].get('youtube_subscribers', 0)
                                ]) if metrics_summary.get('current_month') else 0,
                                'playlist_views': metrics_summary['current_month'].get('playlist_views', 0) if metrics_summary.get('current_month') else 0,
                                'month': metrics_summary['current_month'].get('month', timezone.now().strftime('%Y-%m')) if metrics_summary.get('current_month') else None
                            },
                            'previous_month': {
                                'fan_engagement': float(metrics_summary.get('previous_month', {}).get('fan_engagement_rate', 0)) if metrics_summary.get('previous_month') else 0,
                                'social_following': sum([
                                    metrics_summary['previous_month'].get('instagram_followers', 0),
                                    metrics_summary['previous_month'].get('tiktok_followers', 0),
                                    metrics_summary['previous_month'].get('spotify_followers', 0),
                                    metrics_summary['previous_month'].get('youtube_subscribers', 0)
                                ]) if metrics_summary.get('previous_month') else 0,
                                'playlist_views': metrics_summary['previous_month'].get('playlist_views', 0) if metrics_summary.get('previous_month') else 0,
                                'month': metrics_summary['previous_month'].get('month', (timezone.now() - timedelta(days=30)).strftime('%Y-%m')) if metrics_summary.get('previous_month') else None
                            },
                            'changes': {
                                'fan_engagement': float(metrics_summary.get('engagement_change', 0)),
                                'social_growth': float(metrics_summary.get('social_growth', 0)),
                                'playlist_views': float(metrics_summary.get('playlist_views_change', 0))
                            }
                        }
                except Exception as e:
                    logger.error(f"Error getting metrics summary for artist {getattr(self, 'id', 'unknown')}: {str(e)}")
            
            return response_data
            
        except Exception as e:
            error_msg = f"Error updating metrics for artist {getattr(self, 'id', 'unknown')}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                'success': False,
                'message': str(e),
                'code': 'update_failed'
            }
            
    def _update_buzz_score(self, monthly_listeners, total_streams):
        """
        Calculate and update the artist's buzz score based on various metrics.
        The score is calculated on a scale of 0-100, where 70+ is considered "On Fire".
        
        Args:
            monthly_listeners (int): Number of monthly listeners
            total_streams (int): Total number of streams
        """
        # Initialize score components
        score_components = {
            'follower_growth': 0,      # Based on follower growth rate (if available)
            'engagement': 0,           # Based on engagement rate
            'recent_activity': 0,     # Based on recent releases/activity
            'playlist_performance': 0, # Based on playlist adds/performance
            'consistency': 0          # Based on consistency across platforms
        }
        
        # 1. Follower Growth (25% weight)
        # Calculate based on total social media followers
        total_followers = (
            (self.instagram_followers or 0) + 
            (self.tiktok_followers or 0) + 
            (self.spotify_followers or 0) + 
            (self.youtube_subscribers or 0)
        )
        
        # Simple tiered approach based on follower count
        if total_followers > 1000000:
            score_components['follower_growth'] = 100
        elif total_followers > 500000:
            score_components['follower_growth'] = 80
        elif total_followers > 100000:
            score_components['follower_growth'] = 60
        elif total_followers > 50000:
            score_components['follower_growth'] = 40
        elif total_followers > 10000:
            score_components['follower_growth'] = 20
        else:
            score_components['follower_growth'] = 10
        
        # 2. Engagement (25% weight)
        # Use the pre-calculated fan_engagement_pct field
        score_components['engagement'] = min(100, max(0, self.fan_engagement_pct or 0))
        
        # 3. Recent Activity (20% weight)
        # This would ideally use actual activity data, but for now we'll use streams as a proxy
        streams_millions = (total_streams or 0) / 1000000
        if streams_millions > 100:
            score_components['recent_activity'] = 100
        elif streams_millions > 50:
            score_components['recent_activity'] = 80
        elif streams_millions > 10:
            score_components['recent_activity'] = 60
        elif streams_millions > 1:
            score_components['recent_activity'] = 40
        elif streams_millions > 0.1:
            score_components['recent_activity'] = 20
        else:
            score_components['recent_activity'] = 10
        
        # 4. Playlist Performance (15% weight)
        # Use the pre-calculated playlist_views_pct field
        score_components['playlist_performance'] = min(100, max(0, self.playlist_views_pct or 0))
        
        # 5. Consistency (15% weight)
        # Check if artist has presence across multiple platforms
        platform_count = sum([
            1 if getattr(self, f'{platform}_followers', 0) > 0 else 0 
            for platform in ['instagram', 'tiktok', 'spotify', 'youtube']
        ])
        
        # Score based on number of platforms with presence
        if platform_count >= 4:
            score_components['consistency'] = 100
        elif platform_count == 3:
            score_components['consistency'] = 75
        elif platform_count == 2:
            score_components['consistency'] = 50
        else:
            score_components['consistency'] = 25
        
        # Calculate weighted score (0-100 scale)
        weights = {
            'follower_growth': 0.25,
            'engagement': 0.25,
            'recent_activity': 0.20,
            'playlist_performance': 0.15,
            'consistency': 0.15
        }
        
        # Calculate weighted sum (0-100 scale)
        new_buzz_pct = sum(
            score * weights[component] 
            for component, score in score_components.items()
        )
        
        # Ensure score is within bounds (0-100)
        new_buzz_pct = max(0, min(100, new_buzz_pct))
        
        # Only update if changed significantly to avoid unnecessary saves
        if abs((self.buzz_score_pct or 0) - new_buzz_pct) > 1.0:  # 1% threshold
            self.buzz_score_pct = round(new_buzz_pct, 1)
        
        # Update onFireStatus (threshold is 70/100 = 70%)
        self.onFireStatus = new_buzz_pct >= 70

    def get_current_month_metrics(self):
        """Get or create metrics for the current month."""
        today = timezone.now().date()
        current_month = today.replace(day=1)
        
        # Try to get existing metrics for this month
        metrics, created = ArtistMonthlyMetrics.objects.get_or_create(
            artist=self,
            month=current_month,
            defaults={
                'monthly_listeners': self.monthly_listeners or 0,
                'streams': self.streams or 0,
                'instagram_followers': self.instagram_followers or 0,
                'tiktok_followers': self.tiktok_followers or 0,
                'spotify_followers': self.spotify_followers or 0,
                'youtube_subscribers': self.youtube_subscribers or 0,
                'playlist_views': self.playlist_views or 0,
            }
        )
        
        # If not created, update with latest values
        if not created:
            update_fields = []
            
            # Only update fields that have changed
            if metrics.monthly_listeners != self.monthly_listeners:
                metrics.monthly_listeners = self.monthly_listeners or 0
                update_fields.append('monthly_listeners')
                
            if metrics.streams != self.streams:
                metrics.streams = self.streams or 0
                update_fields.append('streams')
                
            if metrics.instagram_followers != self.instagram_followers:
                metrics.instagram_followers = self.instagram_followers or 0
                update_fields.append('instagram_followers')
                
            if metrics.tiktok_followers != self.tiktok_followers:
                metrics.tiktok_followers = self.tiktok_followers or 0
                update_fields.append('tiktok_followers')
                
            if metrics.spotify_followers != self.spotify_followers:
                metrics.spotify_followers = self.spotify_followers or 0
                update_fields.append('spotify_followers')
                
            if metrics.youtube_subscribers != self.youtube_subscribers:
                metrics.youtube_subscribers = self.youtube_subscribers or 0
                update_fields.append('youtube_subscribers')
                
            if metrics.playlist_views != self.playlist_views:
                metrics.playlist_views = self.playlist_views or 0
                update_fields.append('playlist_views')
            
            if update_fields:
                # Add fan_engagement_rate to update_fields to ensure it's recalculated
                update_fields.extend(['fan_engagement_rate', 'social_growth_rate', 'updated_at'])
                metrics.save(update_fields=update_fields)
        
        return metrics
    
    def get_metrics_history(self, months=12):
        """Get historical metrics for the specified number of months."""
        end_date = timezone.now().date().replace(day=1)
        start_date = (end_date - timedelta(days=30*months)).replace(day=1)
        
        return self.monthly_metrics.filter(
            month__gte=start_date,
            month__lte=end_date
        ).order_by('month')
    
    def calculate_change(self, current, previous):
        """
        Calculate the percentage change between two values.
        
        Args:
            current (float): Current value
            previous (float): Previous value
            
        Returns:
            float: Percentage change (rounded to 2 decimal places)
        """
        if previous == 0:
            return 0.0
        return round(((current - previous) / previous) * 100, 2)
        
    def get_metrics_summary(self):
        """
        Get a summary of the artist's current metrics and their trends.
        Returns a dictionary with current metrics and their changes from the previous period.
        """
        current_metrics = {
            'fan_engagement_pct': self.fan_engagement_pct or 0.0,
            'social_following_pct': self.social_following_pct or 0.0,
            'playlist_views_pct': self.playlist_views_pct or 0.0,
            'buzz_score_pct': self.buzz_score_pct or 0.0,
        }
        
        # Get the most recent monthly metrics for comparison
        monthly_metrics = self.monthly_metrics.order_by('-month').first()
        
        if monthly_metrics:
            previous_metrics = {
                'fan_engagement_pct': monthly_metrics.fan_engagement_pct,
                'social_following_pct': monthly_metrics.social_following_pct,
                'playlist_views_pct': monthly_metrics.playlist_views_pct,
                'buzz_score_pct': monthly_metrics.buzz_score_pct,
            }
        else:
            # If no monthly metrics exist, use current values with 0 changes
            previous_metrics = current_metrics.copy()
        
        # Calculate percentage changes
        changes = {
            'fan_engagement': self.calculate_change(
                current_metrics['fan_engagement_pct'], 
                previous_metrics['fan_engagement_pct']
            ),
            'social_following': self.calculate_change(
                current_metrics['social_following_pct'], 
                previous_metrics['social_following_pct']
            ),
            'playlist_views': self.calculate_change(
                current_metrics['playlist_views_pct'], 
                previous_metrics['playlist_views_pct']
            ),
            'buzz_score': self.calculate_change(
                current_metrics['buzz_score_pct'], 
                previous_metrics['buzz_score_pct']
            ),
        }
        
        # Update onFireStatus based on 9% or more increase in buzz score
        buzz_score_change = changes['buzz_score']
        self.onFireStatus = buzz_score_change >= 9.0  # 9% or more increase triggers on fire status
        
        return {
            'current': current_metrics,
            'previous': previous_metrics,
            'changes': changes,
            'on_fire': self.onFireStatus,
            'last_updated': self.last_metrics_update.isoformat() if self.last_metrics_update else None
        }
    
    def save(self, *args, **kwargs):
        # Check if any metrics have changed
        metrics_changed = any(
            self.metrics_tracker.has_changed(field)
            for field in self.metrics_tracker.fields
        )
        
        # Call the parent save first to ensure the instance is saved
        super().save(*args, **kwargs)
        
        # If metrics changed, update the current month's metrics
        if metrics_changed and any(field in self.metrics_tracker.changed() for field in [
            'monthly_listeners', 'streams', 'instagram_followers', 
            'tiktok_followers', 'spotify_followers', 'youtube_subscribers',
            'playlist_views'
        ]):
            self.get_current_month_metrics()
        
        # If metrics changed, trigger an async update using thread-based task
        if metrics_changed:
            try:
                from artists.tasks import update_artist_metrics
                from utils.tasks import run_async
                run_async(update_artist_metrics, artist_id=self.id)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Error scheduling metrics update: {str(e)}")

    def can_invite(self, target_tier):
        INVITATION_RULES = {
            'GOLIATH': ['ROCKSTAR', 'SCENE_KING', 'UP_AND_COMING', 'NEW_BLOOD', 'FRESH_TALENT'],
            'ROCKSTAR': ['SCENE_KING', 'UP_AND_COMING', 'NEW_BLOOD', 'FRESH_TALENT'],
            'SCENE_KING': ['UP_AND_COMING', 'NEW_BLOOD', 'FRESH_TALENT'],
            'UP_AND_COMING': ['NEW_BLOOD', 'FRESH_TALENT'],
            'NEW_BLOOD': ['FRESH_TALENT'],
            'FRESH_TALENT': []
        }
        return target_tier in INVITATION_RULES.get(self.performance_tier, [])


class Venue(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='venue_profile')
    verification_docs = models.FileField(
                upload_to='venue_verification_docs', blank=True, null=True)
    location = models.JSONField(default=list)
    capacity = models.IntegerField(default=0)
    amenities = models.JSONField(default=list)
    PROOF_CHOICES = [
        ('DOCUMENT', 'Document'),
        ('URL', 'URL'),
    ]

    proof_type = models.CharField(max_length=10, choices=PROOF_CHOICES, null=True, blank=True)
    proof_document = models.FileField(upload_to='venue_proofs/', null=True, blank=True)
    proof_url = models.URLField(null=True, blank=True)

    seating_plan = models.ImageField(
        upload_to='venue_seating_plan', 
        blank=True, 
        null=True,
        help_text="Upload a seating plan for the venue"
    )
    reservation_fee = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0,
        help_text="Base reservation fee for the venue"
    )
    address = models.CharField(
        max_length=255, 
        blank=True, 
        null=True,
        help_text="Physical address of the venue"
    )
    artist_capacity = models.IntegerField(
        default=0,
        help_text="Maximum number of artists that can perform at the venue"
    )
    is_completed = models.BooleanField(
        default=False,
        help_text="Whether the venue profile is fully set up"
    )
    stripe_account_id = models.CharField(
        max_length=255, 
        blank=True, 
        null=True, 
        default=None,
        help_text="Stripe Connect account ID for payments"
    )
    stripe_onboarding_completed = models.BooleanField(
        default=False,
        help_text="Whether Stripe onboarding is completed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    logo = models.ImageField(upload_to='venue_logos/', blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    tier = models.ForeignKey(
        'VenueTier',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="The venue's performance tier based on capacity"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Venue'
        verbose_name_plural = 'Venues'

    def __str__(self):
        return f"{self.user.name} - {self.tier.get_tier_display() if self.tier else 'No Tier'}"




    def get_dirty_fields(self):
        """
        Get a dictionary of fields that have been modified since the model was instantiated.
        Returns a dictionary where keys are field names and values are the original values.
        """
        if not hasattr(self, '_original_state'):
            # Initialize with current state if not already done
            self._original_state = {}
            for field in self._meta.fields:
                self._original_state[field.name] = getattr(self, field.name)
        
        dirty_fields = {}
        for field_name, original_value in self._original_state.items():
            current_value = getattr(self, field_name)
            if current_value != original_value:
                dirty_fields[field_name] = original_value
        
        return dirty_fields
    
    def save(self, *args, **kwargs):
        # Check if capacity has changed
        if hasattr(self, '_original_state') and 'capacity' in self._original_state:
            if self._original_state['capacity'] != self.capacity:
                # Capacity has changed, update the tier
                self.tier = VenueTier.get_tier_for_capacity(self.capacity)
        
        # Save the model
        super().save(*args, **kwargs)
        
        # Clean up
        if hasattr(self, '_original_state'):
            delattr(self, '_original_state')
    
    def get_eligible_artist_tiers(self):
        """Get list of artist tiers that can perform at this venue"""
        if not self.tier:
            return []
            
        # Get all artist tiers that include this venue tier in their eligible venues
        eligible_tiers = []
        for artist_tier_name, venue_tier_names in _TierConfig.ARTIST_VENUE_MAPPING.items():
            if self.tier.tier in venue_tier_names:
                eligible_tiers.append(artist_tier_name)
                
        return eligible_tiers
    
    def can_host_artist(self, artist):
        """Check if this venue can host a specific artist"""
        if not self.tier or not hasattr(artist, 'performance_tier'):
            return False
            
        # Get the artist's tier name
        artist_tier_name = artist.performance_tier.name if artist.performance_tier else None
        if not artist_tier_name:
            return False
            
        # Check if the artist's tier is in the venue's eligible tiers
        return artist_tier_name in self.get_eligible_artist_tiers()
    


class Fan(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.name}'
