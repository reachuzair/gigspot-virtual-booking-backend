from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
import random
import logging

logger = logging.getLogger(__name__)


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


class SubscriptionTier(models.TextChoices):
    STARTER = 'starter', 'Starter'
    ESSENTIAL = 'essential', 'Essential'
    PRO = 'pro', 'Pro'
    ELITE = 'elite', 'Elite'


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
        choices=SubscriptionTier.choices, 
        default=SubscriptionTier.STARTER,
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
    follower_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of followers from SoundCharts"
    )
    buzz_score = models.IntegerField(
        default=0,
        help_text="Artist's buzz score for trending"
    )
    onFireStatus = models.BooleanField(
        default=False,
        help_text="Whether the artist is currently trending"
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

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Artist'
        verbose_name_plural = 'Artists'
        indexes = [
            models.Index(fields=['performance_tier']),
            models.Index(fields=['subscription_tier']),
            models.Index(fields=['buzz_score']),
        ]

    def __str__(self):
        return f"{self.display_name} - {self.get_performance_tier_display()}"
        
    @property
    def display_name(self):
        """Get the display name (band name or user name)"""
        return self.band_name or self.user.name

    def update_metrics_from_soundcharts(self, force_update=False):
        """
        Update artist metrics using SoundCharts API
        
        Args:
            force_update (bool): If True, force update even if recently updated
            
        Returns:
            dict: Result of the update with status and data
        """
        if not self.soundcharts_uuid:
            return {
                'success': False,
                'error': 'No SoundCharts UUID set for this artist',
                'code': 'missing_uuid'
            }
            
        # Check if we recently updated (within 24 hours)
        if not force_update and self.last_tier_update:
            time_since_update = timezone.now() - self.last_tier_update
            if time_since_update < timedelta(hours=24):
                return {
                    'success': True,
                    'tier': self.performance_tier,
                    'tier_display': self.get_performance_tier_display(),
                    'last_updated': self.last_tier_update.isoformat(),
                    'message': 'Using cached data (updated recently)',
                    'cached': True
                }

        from services.soundcharts import SoundChartsAPI
        try:
            soundcharts = SoundChartsAPI()
            
            # Get artist summary for followers and other metrics
            summary_endpoint = f"{soundcharts.BASE_URL}/artist/{self.soundcharts_uuid}/summary"
            summary = soundcharts._make_request(summary_endpoint)
            
            if 'error' in summary:
                return {
                    'success': False,
                    'error': summary['error'],
                    'code': 'soundcharts_error'
                }
                
            # Extract metrics
            follower_count = summary.get('followerCount', 0)
            monthly_listeners = summary.get('monthlyListeners', 0)
            total_stream_count = summary.get('totalStreamCount', 0)
            
            # Update artist fields
            self.follower_count = follower_count
            self.performance_tier = PerformanceTier.get_artist_tier(follower_count)
            self.last_tier_update = timezone.now()
            
            # Save the updated fields
            update_fields = [
                'follower_count', 
                'performance_tier', 
                'last_tier_update',
                'updated_at'
            ]
            
            # Update buzz score based on metrics
            self._update_buzz_score(monthly_listeners, total_stream_count)
            if hasattr(self, '_buzz_updated'):
                update_fields.append('buzz_score')
            
            self.save(update_fields=update_fields)
            
            return {
                'success': True,
                'tier': self.performance_tier,
                'tier_display': self.get_performance_tier_display(),
                'follower_count': self.follower_count,
                'last_updated': self.last_tier_update.isoformat(),
                'metrics': {
                    'monthly_listeners': monthly_listeners,
                    'total_streams': total_stream_count
                }
            }
            
        except Exception as e:
            logger.error(f"Error updating artist metrics from SoundCharts: {e}", 
                       exc_info=True)
            return {
                'success': False,
                'error': str(e),
                'code': 'update_error'
            }
            
    def _update_buzz_score(self, monthly_listeners, total_streams):
        """Calculate and update the artist's buzz score"""
        # Simple algorithm - can be enhanced based on business requirements
        # This is a placeholder - adjust weights as needed
        
        # Reset buzz score
        new_buzz = 0
        
        # Add points based on follower growth rate (if we had historical data)
        # For now, just use current follower count
        if self.follower_count > 0:
            if self.follower_count > 1000000:
                new_buzz += 50
            elif self.follower_count > 500000:
                new_buzz += 40
            elif self.follower_count > 100000:
                new_buzz += 30
            elif self.follower_count > 50000:
                new_buzz += 20
            elif self.follower_count > 10000:
                new_buzz += 10
                
        # Add points based on monthly listeners
        if monthly_listeners > 1000000:
            new_buzz += 30
        elif monthly_listeners > 500000:
            new_buzz += 25
        elif monthly_listeners > 100000:
            new_buzz += 20
        elif monthly_listeners > 50000:
            new_buzz += 15
        elif monthly_listeners > 10000:
            new_buzz += 10
            
        # Add points based on total streams (in millions)
        streams_millions = total_streams / 1000000
        if streams_millions > 100:
            new_buzz += 20
        elif streams_millions > 50:
            new_buzz += 15
        elif streams_millions > 10:
            new_buzz += 10
        elif streams_millions > 1:
            new_buzz += 5
            
        # Cap at 100
        new_buzz = min(100, new_buzz)
        
        # Only update if changed significantly to avoid unnecessary saves
        if abs(self.buzz_score - new_buzz) > 2:
            self.buzz_score = new_buzz
            self._buzz_updated = True
            
        # Update onFireStatus based on buzz
        self.onFireStatus = self.buzz_score >= 70

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
    user = models.OneToOneField(User, on_delete=models.CASCADE)
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

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Venue'
        verbose_name_plural = 'Venues'

    def __str__(self):
        return f"{self.user.name} - {self.get_performance_tier_display()}"

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
        # Auto-set venue tier based on capacity
        if self.capacity is not None and (self._state.adding or 'capacity' in self.get_dirty_fields()):
            self.tier = VenueTier.get_tier_for_capacity(self.capacity)
        
        # Update the original state after saving
        super().save(*args, **kwargs)
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
