from django.db import models
import stripe
from django.conf import settings
from custom_auth.models import SubscriptionTier
from datetime import datetime
from django.utils.translation import gettext_lazy as _

stripe.api_key = settings.STRIPE_SECRET_KEY


class SubscriptionStatus(models.TextChoices):
    """Status choices for subscriptions."""
    ACTIVE = 'active', _('Active')
    CANCELED = 'canceled', _('Canceled')
    INCOMPLETE = 'incomplete', _('Incomplete')
    INCOMPLETE_EXPIRED = 'incomplete_expired', _('Incomplete Expired')
    PAST_DUE = 'past_due', _('Past Due')
    PAUSED = 'paused', _('Paused')
    TRIALING = 'trialing', _('Trialing')
    UNPAID = 'unpaid', _('Unpaid')
    INACTIVE = 'inactive', _('Inactive')

class SubscriptionPlan(models.Model):
    """
    Stores the Stripe subscription plan details for artists
    """
    TIER_CHOICES = [
        ('FREE', 'Free'),
        ('PREMIUM', 'Premium')
    ]
    
    subscription_tier = models.CharField(
        max_length=255, 
        choices=TIER_CHOICES,
    )
    stripe_price_id = models.CharField(max_length=100, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    billing_interval = models.CharField(
        max_length=20,
        choices=[('month', 'Monthly'), ('year', 'Yearly')],
        default='month'
    )
    features = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    FEATURE_MAP = {
        'FREE': {
            'description': 'Free Starter Plan for emerging or part-time artists',
            'price': 0.00,
            'billing_interval': 'month',
            'features': [
                'Basic Artist Profile with bio, photos, and music links',
                'Connect social media accounts',
                'Public Artist Page with basic stats and past shows',
                'Join 1 show per calendar month',
                'View upcoming tour opportunities (read-only)',
                'Basic analytics for your gigs (ticket sales, attendance)',
                'Fan engagement through messages/comments',
                'Basic BuzzScore tracking (current score and trend only)'
            ],
            'max_shows': 1,
            'max_shows_period_days': 30,
            'create_tour': False,
            'create_show': True,
            'merch_store': False,
            'analytics': 'basic',
            'buzz_score': 'basic_view',
            'can_message_fans': True,
            'can_view_tours': True,
            'can_join_tours': False,
            'can_create_tours': False,
            'priority_support': False,
        },
        'PREMIUM': {
            'description': 'Professional artist tools for serious musicians',
            'price': 20.00,
            'billing_interval': 'month',
            'features': [
                'Unlimited show applications',
                'Create and manage tours with AI/Manual route planning',
                'Sell merchandise and digital products',
                'Automated promotional scheduler with AI content',
                'Advanced BuzzScore analytics and optimization',
                'Priority customer support',
                'All features from FREE tier'
            ],
            'max_shows': None,  
            'create_tour': True,
            'create_show': True,
            'merch_store': True,
            'analytics': 'advanced',
            'buzz_score': 'full_analytics',
            'can_message_fans': True,
            'can_view_tours': True,
            'can_join_tours': True,
            'can_create_tours': True,
            'priority_support': True,
        }
    }
    def __str__(self):
        return f"{self.get_subscription_tier_display()} - ${self.price}/{self.billing_interval}"
        
    @property
    def can_create_show(self):
        """Check if artist can create a new show based on their subscription"""
        if self.subscription_tier == 'FREE':
            from datetime import datetime, timedelta
            from django.utils import timezone
            from gigs.models import Gig  # Assuming this is the correct import path
            
            # Count shows in the last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            show_count = Gig.objects.filter(
                artist=self.artist,
                created_at__gte=thirty_days_ago
            ).count()
            
            return show_count < self.FEATURE_MAP['FREE']['max_shows']
        return True
    
    def save(self, *args, **kwargs):
        self.features = self.FEATURE_MAP.get(self.subscription_tier, {})
        super().save(*args, **kwargs)
        
    def can_create_tour(self):
        """
        Check if the artist can create a tour based on their subscription.
        Only premium users can create tours.
        """
        return self.subscription_tier == 'PREMIUM' and self.status == 'active'

class VenueAdTier(models.TextChoices):
    STARTER = 'STARTER', 'Starter'
    BOOSTED = 'BOOSTED', 'Boosted'
    PREMIUM = 'PREMIUM', 'Premium'

class VenueAdPlan(models.Model):
    """
    Stores the venue ad subscription plans with their pricing and features
    """
    name = models.CharField(
        max_length=100,
        choices=VenueAdTier.choices,
        unique=True
    )
    description = models.TextField(blank=True)
    
    # Pricing
    weekly_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    monthly_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Stripe IDs
    weekly_stripe_price_id = models.CharField(max_length=100, blank=True, null=True)
    monthly_stripe_price_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Features
    features = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Feature mapping for each tier
    FEATURE_MAP = {
            'STARTER': {
                'description': 'Basic visibility for your venue',
                'weekly_price': 25.00,
                'monthly_price': 75.00,
                'features': [
                    'Appear as "Suggested Venue" in artist dashboards',
                    'Appear in city searches',
                    'Basic venue profile visibility'
                ],
                'priority_in_search': False,
                'custom_map_pin': False,
                'homepage_feature': False,
                'email_spotlight': False,
                'analytics_access': False,
                'promo_analytics': False
            },
            'BOOSTED': {
                'description': 'Increased visibility for your venue',
                'weekly_price': 37.50,  # 150/4 weeks
                'monthly_price': 150.00,
                'features': [
                    'Priority spot on map',
                    'Always shown first in matching tier searches',
                    'All Starter tier features',
                    'Highlighted in search results'
                ],
                'priority_in_search': True,
                'custom_map_pin': True,
                'homepage_feature': False,
                'email_spotlight': False,
                'analytics_access': True,
                'promo_analytics': True
            },
            'PREMIUM': {
                'description': 'Maximum visibility and premium placement',
                'weekly_price': 62.50,  # 250/4 weeks
                'monthly_price': 250.00,
                'features': [
                    'Featured slot on home dashboard',
                    'All Boosted tier features',
                    'Premium badge on profile',
                    'Priority support',
                    'Featured in weekly newsletter'
                ],
                'priority_in_search': True,
                'custom_map_pin': True,
                'homepage_feature': True,
                'email_spotlight': True,
                'analytics_access': True,
                'promo_analytics': True
            }
        }
    
    def __str__(self):
        return f"{self.get_name_display()} - ${self.monthly_price}/month"
    
    def save(self, *args, **kwargs):
        # Auto-populate fields based on the selected tier
        if self.name in self.FEATURE_MAP:
            tier_data = self.FEATURE_MAP[self.name]
            self.description = tier_data['description']
            self.weekly_price = tier_data.get('weekly_price')
            self.monthly_price = tier_data['monthly_price']
            self.features = tier_data['features']
        super().save(*args, **kwargs)


class VenueSubscription(models.Model):
    """
    Tracks a venue's ad subscription status
    """
    SUBSCRIPTION_STATUS = [
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('incomplete', 'Incomplete'),
        ('incomplete_expired', 'Incomplete Expired'),
        ('past_due', 'Past Due'),
        ('paused', 'Paused'),
        ('trialing', 'Trialing'),
        ('unpaid', 'Unpaid'),
    ]
    
    BILLING_INTERVAL = [
        ('week', 'Weekly'),
        ('month', 'Monthly'),
    ]
    
    venue = models.ForeignKey('custom_auth.Venue', on_delete=models.CASCADE, related_name='ad_subscriptions')
    plan = models.ForeignKey(VenueAdPlan, on_delete=models.PROTECT)
    
    # Stripe fields
    stripe_customer_id = models.CharField(max_length=100)
    stripe_subscription_id = models.CharField(max_length=100, unique=True)
    stripe_price_id = models.CharField(max_length=100)
    
    # Subscription details
    status = models.CharField(max_length=20, choices=SUBSCRIPTION_STATUS, default='incomplete')
    billing_interval = models.CharField(max_length=10, choices=BILLING_INTERVAL, default='month')
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.venue.user.name} - {self.plan.get_name_display()} ({self.get_status_display()})"
    
    @property
    def is_active(self):
        return self.status in ['active', 'trialing']
    
    def update_from_stripe(self, stripe_subscription):
        """
        Update subscription details from Stripe webhook data
        """
        from django.utils.timezone import make_aware
        
        self.status = stripe_subscription.status
        self.current_period_start = make_aware(datetime.fromtimestamp(stripe_subscription.current_period_start))
        self.current_period_end = make_aware(datetime.fromtimestamp(stripe_subscription.current_period_end))
        self.cancel_at_period_end = stripe_subscription.cancel_at_period_end
        
        if stripe_subscription.canceled_at:
            self.canceled_at = make_aware(datetime.fromtimestamp(stripe_subscription.canceled_at))
        
        self.save()
        return self

class ArtistSubscription(models.Model):
    """
    Tracks a artist's subscription status
    """
    artist = models.OneToOneField('custom_auth.Artist', on_delete=models.CASCADE, related_name='subscription')
    stripe_customer_id = models.CharField(max_length=100)
    stripe_subscription_id = models.CharField(max_length=100)
    plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, default='inactive')
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.artist.user.name} - {self.plan}"

    def update_from_stripe(self):
        """Sync with Stripe subscription data"""
        try:
            stripe_sub = stripe.Subscription.retrieve(self.stripe_subscription_id)
            self.status = stripe_sub.status
            self.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
            self.cancel_at_period_end = stripe_sub.cancel_at_period_end
            self.save()
            return True
        except stripe.error.StripeError as e:
            # Handle error or log it
            return False