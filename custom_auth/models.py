from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from datetime import timedelta
from django.utils.text import slugify
import random

class UserManager(BaseUserManager):
    def create_user(self, username, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(username, email, password, **extra_fields)

class ROLE_CHOICES(models.TextChoices):
    ARTIST = 'artist', 'Artist'
    VENUE = 'venue', 'Venue'
    FAN = 'fan', 'Fan'

def user_profile_image_path(instance, filename):
    # Generate a unique filename using username and timestamp
    import time
    timestamp = int(time.time())
    extension = filename.split('.')[-1].lower()
    new_filename = f"{slugify(instance.username)}_{timestamp}.{extension}"
    return f'profile_images/{new_filename}'

class User(AbstractBaseUser, PermissionsMixin):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=255, unique=True)
    name = models.CharField(max_length=255, default="")
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=255, choices=ROLE_CHOICES.choices, default=ROLE_CHOICES.FAN)
    profileCompleted = models.BooleanField(default=False)
    profileImage = models.ImageField(upload_to=user_profile_image_path, blank=True, null=True, default=None)
    ver_code = models.CharField(max_length=255, blank=True, null=True)
    ver_code_expires = models.DateTimeField(blank=True, null=True)
    email_verfied = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)  # Required for Django admin
    is_active = models.BooleanField(default=True)  # Required for Django admin
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'  # Use email as the unique identifier for authentication
    REQUIRED_FIELDS = ['username']  # Fields required when creating a user via createsuperuser

    def __str__(self):
        return self.username
    
    def gen_otp(self):
        """Generate a 6-digit numeric OTP and save it with an expiry date."""
        otp = random.randint(100000, 999999)  # Generate a random number between 100000 and 999999
        self.ver_code = otp  # Save OTP to ver_code field
        self.ver_code_expires = timezone.now() + timedelta(minutes=60)  # Set expiry to 60 minutes from now
        self.save()  # Save the user instance to persist changes
        return otp

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
    verification_docs = models.FileField(upload_to='artist_verification_docs', blank=True, null=True)
    logo = models.ImageField(upload_to='artist_logo', blank=True, null=True)
    band_name = models.CharField(max_length=255, blank=True, null=True)
    band_email = models.EmailField(blank=True, null=True)
    state = models.CharField(max_length=255, blank=True, null=True)
    performance_tier = models.CharField(max_length=255, choices=PerformanceTier.choices, default=PerformanceTier.FRESH_TALENT)
    subscription_tier = models.CharField(max_length=255, choices=SubscriptionTier.choices, default=SubscriptionTier.STARTER)
    buzz_score = models.IntegerField(default=0)
    onFireStatus = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'

class Venue(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    verification_docs = models.FileField(upload_to='venue_verification_docs', blank=True, null=True)
    location = models.JSONField(default=list)
    capacity = models.IntegerField(default=0)
    amenities = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class Fan(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.first_name} {self.last_name}'


