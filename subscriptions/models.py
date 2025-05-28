# Add to your models.py
from django.db import models
import stripe
from django.conf import settings
from custom_auth.models import SubscriptionTier
from datetime import datetime

stripe.api_key = settings.STRIPE_SECRET_KEY

class SubscriptionPlan(models.Model):
    """
    Stores the Stripe subscription plan details that correspond to SubscriptionTier choices
    """
    subscription_tier = models.CharField(
        max_length=255, 
        choices=SubscriptionTier.choices,
        unique=True
    )
    stripe_price_id = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_interval = models.CharField(
        max_length=20,
        choices=[('month', 'Monthly'), ('year', 'Yearly')],
        default='month'
    )
    features = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    FEATURE_MAP = {
        'STARTER': {
            'max_shows': 1,
            'create_tour': False,
            'create_show': False,
            'merch_store': False,
            'ai_promo': False,
            'analytics': 'basic',
            'payout_type': 'manual',
        },
        'ESSENTIAL': {
            'max_shows': 6,
            'create_tour': False,
            'create_show': True,
            'merch_store': False,
            'ai_promo': False,
            'analytics': 'basic',
            'payout_type': 'scheduled',
        },
        'PRO': {
            'max_shows': None,  # unlimited
            'create_tour': True,
            'create_show': True,
            'merch_store': True,
            'ai_promo': True,
            'analytics': 'advanced',
            'payout_type': 'scheduled',
        },
        'ELITE': {
            'max_shows': None,
            'create_tour': True,
            'create_show': True,
            'merch_store': True,
            'ai_promo': True,
            'analytics': 'premium',
            'payout_type': 'instant',
        }
    }
    def __str__(self):
        return f"{self.get_subscription_tier_display()} - ${self.price}/{self.billing_interval}"
    
    def save(self, *args, **kwargs):
        self.features = self.FEATURE_MAP.get(self.subscription_tier, {})
        super().save(*args, **kwargs)

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