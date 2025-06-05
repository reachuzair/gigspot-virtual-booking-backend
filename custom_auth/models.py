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
    REQUIRED_FIELDS = ['name']

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


class PerformanceTier(models.TextChoices):
    FRESH_TALENT = 'fresh_talent', 'Fresh Talent (0-1k followers)'
    NEW_BLOOD = 'new_blood', 'New Blood (1k-10k followers)'
    UP_AND_COMING = 'up_and_coming', 'Up and Coming (10k-50k followers)'
    RISING_STAR = 'rising_star', 'Rising Star (50k-200k followers)'
    SCENE_KING = 'scene_king', 'Scene King (200k-500k followers)'
    ROCKSTAR = 'rockstar', 'Rockstar (500k-1M followers)'
    GOLIATH = 'goliath', 'Goliath (1M+ followers)'

    @classmethod
    def get_tier_for_followers(cls, follower_count):
        if follower_count >= 1000000:
            return cls.GOLIATH
        elif follower_count >= 500000:
            return cls.ROCKSTAR
        elif follower_count >= 200000:
            return cls.SCENE_KING
        elif follower_count >= 50000:
            return cls.RISING_STAR
        elif follower_count >= 10000:
            return cls.UP_AND_COMING
        elif follower_count >= 1000:
            return cls.NEW_BLOOD
        return cls.FRESH_TALENT


class VenueTier(models.Model):
    TIER_CHOICES = [
        ('CLASS_IA', 'Class I-A (Small Local Venues)'),
        ('CLASS_IIA', 'Class II-A (Mid-Sized Growth Venues)'),
        ('CLASS_IIIA', 'Class III-A (Regional Venues)'),
        ('CLASS_IVA', 'Class IV-A (Major Music Halls & Theaters)'),
        ('CLASS_VA', 'Class V-A (Premier National Venues)'),
        ('CLASS_VIA', 'Class VI-A (Stadiums & Arenas)'),
    ]
    
    tier = models.CharField(max_length=50, choices=TIER_CHOICES, unique=True)
    min_capacity = models.PositiveIntegerField(help_text="Minimum capacity for this venue tier")
    max_capacity = models.PositiveIntegerField(help_text="Maximum capacity for this venue tier")
    eligible_artist_tiers = models.JSONField(
        help_text="List of artist tiers that can perform at this venue",
        default=list
    )
    description = models.TextField(blank=True, help_text="Description of the venue tier")
    example_venues = models.TextField(help_text="Example venues that fall into this tier")
    
    class Meta:
        ordering = ['min_capacity']
        verbose_name = 'Venue Tier'
        verbose_name_plural = 'Venue Tiers'
    
    def __str__(self):
        return self.get_tier_display()
    
    @classmethod
    def get_eligible_venues_for_artist_tier(cls, artist_tier):
        """
        Get all venue tiers that are eligible for a specific artist tier
        """
        return cls.objects.filter(eligible_artist_tiers__contains=[artist_tier])
    
    @classmethod
    def get_tier_for_capacity(cls, capacity):
        """
        Get the appropriate venue tier based on capacity
        """
        return cls.objects.filter(
            min_capacity__lte=capacity,
            max_capacity__gte=capacity
        ).first()


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
    objects = ArtistManager()
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=255, blank=True, null=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    verification_docs = models.FileField(
        upload_to='artist_verification_docs', blank=True, null=True)
    logo = models.ImageField(upload_to='artist_logo', blank=True, null=True)
    band_name = models.CharField(max_length=255, blank=True, null=True)
    band_email = models.EmailField(blank=True, null=True)
    city = models.CharField(max_length=255, blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    performance_tier = models.CharField(
        max_length=255, choices=PerformanceTier.choices, default=PerformanceTier.FRESH_TALENT)
    subscription_tier = models.CharField(
        max_length=255, choices=SubscriptionTier.choices, default=SubscriptionTier.STARTER)
    shows_created = models.PositiveIntegerField(default=0)
    active_collaborations = models.ManyToManyField(
        'self', symmetrical=False, related_name='collaborators')
    soundcharts_uuid = models.CharField(
        max_length=255, blank=True, null=True, default=None, unique=True)
    buzz_score = models.IntegerField(default=0)
    onFireStatus = models.BooleanField(default=False)
    connections = models.ManyToManyField(
        'self', symmetrical=False, related_name='artist_connections')
    stripe_account_id = models.CharField(
        max_length=255, blank=True, null=True, default=None)
    stripe_onboarding_completed = models.BooleanField(default=False)
    
    # Metrics fields
    followers = models.PositiveIntegerField(default=0, help_text='Number of followers on streaming platforms')
    monthly_listeners = models.PositiveIntegerField(default=0, help_text='Monthly listeners on streaming platforms')
    total_streams = models.PositiveBigIntegerField(default=0, help_text='Total streams across all platforms')
    last_metrics_update = models.DateTimeField(null=True, blank=True, help_text='When metrics were last updated')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-followers']
        verbose_name = 'Artist'
        verbose_name_plural = 'Artists'

    def __str__(self):
        return f'{self.user.name}'
        
    def update_metrics_from_soundcharts(self):
        """
        Update artist metrics using SoundCharts API
        Returns:
            dict: Result of the update with status and data
        """
        from services.soundcharts import SoundChartsAPI
        
        if not self.soundcharts_uuid:
            return {'success': False, 'error': 'No SoundCharts UUID set for this artist'}
            
        try:
            soundcharts = SoundChartsAPI()
            result = soundcharts.update_artist_tier(self)
            
            if 'error' in result:
                return {'success': False, 'error': result['error']}
                
            self.last_metrics_update = timezone.now()
            self.save(update_fields=['last_metrics_update'])
            
            return {
                'success': True,
                'tier': self.performance_tier,
                'followers': self.followers,
                'monthly_listeners': self.monthly_listeners,
                'total_streams': self.total_streams,
                'last_updated': self.last_metrics_update
            }
            
        except Exception as e:
            logger.error(f"Error updating artist metrics: {str(e)}")
            return {'success': False, 'error': str(e)}

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
    tier = models.ForeignKey(
        VenueTier,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='venues',
        help_text="Automatically set based on capacity"
    )
    amenities = models.JSONField(default=list)
    seating_plan = models.ImageField(
        upload_to='venue_seating_plan', blank=True, null=True)
    reservation_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0)
    address = models.CharField(max_length=255, blank=True, null=True)
    artist_capacity = models.IntegerField(default=0)
    is_completed = models.BooleanField(default=False)
    stripe_account_id = models.CharField(
        max_length=255, blank=True, null=True, default=None)
    stripe_onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.name} - {self.address}"

    def save(self, *args, **kwargs):
        # Auto-assign tier based on capacity
        if not self.tier_id or 'capacity' in kwargs.get('update_fields', []):
            self.tier = VenueTier.get_tier_for_capacity(self.capacity)
        super().save(*args, **kwargs)


class Fan(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.name}'
