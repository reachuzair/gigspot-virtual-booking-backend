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
    FRESH_TALENT = 'fresh_talent', 'Fresh Talent'
    NEW_BLOOD = 'new_blood', 'New Blood'
    UP_AND_COMING = 'up_and_coming', 'Up and Coming'
    RISING_STAR = 'rising_star', 'Rising Star'
    SCENE_KING = 'scene_king', 'Scene King'
    ROCKSTAR = 'rockstar', 'Rockstar'
    GOLIATH = 'goliath', 'Goliath'


class SubscriptionTier(models.TextChoices):
    STARTER = 'starter', 'Starter'
    ESSENTIAL = 'essential', 'Essential'
    PRO = 'pro', 'Pro'
    ELITE = 'elite', 'Elite'


class Artist(models.Model):
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
        max_length=255, blank=True, null=True, default=None)
    buzz_score = models.IntegerField(default=0)
    onFireStatus = models.BooleanField(default=False)
    connections = models.ManyToManyField(
        'self', symmetrical=False, related_name='artist_connections')
    stripe_account_id = models.CharField(
        max_length=255, blank=True, null=True, default=None)
    stripe_onboarding_completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.name}'

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
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    logo = models.ImageField(upload_to='venue_logos/', blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f'{self.user.name}'


class Fan(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.name}'
