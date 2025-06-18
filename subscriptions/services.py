"""Services for handling subscription-related operations."""
import logging
from django.utils import timezone
from django.db import transaction
from .models import (
    SubscriptionPlan,
    VenueAdPlan,
    ArtistSubscription,
    VenueSubscription,
    SubscriptionStatus
)

logger = logging.getLogger(__name__)

class PlanService:
    """Service for handling subscription plan operations."""
    
    @classmethod
    def get_active_plans(cls, plan_model):
        """Get all active subscription plans."""
        return plan_model.objects.filter(is_active=True).order_by('price')
    
    @classmethod
    def get_plan_by_id(cls, plan_model, plan_id):
        """Get a specific plan by ID."""
        try:
            return plan_model.objects.get(id=plan_id, is_active=True)
        except plan_model.DoesNotExist:
            return None


class SubscriptionService:
    """Service for managing subscription state and metadata."""
    
    @classmethod
    def create_subscription(cls, user, plan, subscription_type, stripe_subscription_id):
        """
        Create a new subscription record.
        
        Args:
            user: The user subscribing
            plan: The subscription plan
            subscription_type: 'artist' or 'venue'
            stripe_subscription_id: ID from Stripe
            
        Returns:
            Subscription: The created subscription object
        """
        subscription_class = ArtistSubscription if subscription_type == 'artist' else VenueSubscription
        profile_relation = 'artist_profile' if subscription_type == 'artist' else 'venue_profile'
        
        subscription = subscription_class.objects.create(
            **{profile_relation: getattr(user, profile_relation)},
            plan=plan,
            stripe_subscription_id=stripe_subscription_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),  # Will be updated by webhook
            cancel_at_period_end=False
        )
        return subscription
    
    @classmethod
    def cancel_subscription(cls, subscription_id, subscription_type):
        """
        Mark a subscription for cancellation at period end.
        
        Args:
            subscription_id: ID of the subscription to cancel
            subscription_type: 'artist' or 'venue'
            
        Returns:
            Subscription: The updated subscription object
        """
        subscription_class = ArtistSubscription if subscription_type == 'artist' else VenueSubscription
        
        subscription = subscription_class.objects.get(id=subscription_id)
        subscription.cancel_at_period_end = True
        subscription.status = SubscriptionStatus.CANCELED
        subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
        
        return subscription
    
    @classmethod
    def reactivate_subscription(cls, subscription_id, subscription_type):
        """
        Reactivate a canceled subscription.
        
        Args:
            subscription_id: ID of the subscription to reactivate
            subscription_type: 'artist' or 'venue'
            
        Returns:
            Subscription: The updated subscription object
        """
        subscription_class = ArtistSubscription if subscription_type == 'artist' else VenueSubscription
        
        subscription = subscription_class.objects.get(id=subscription_id)
        subscription.cancel_at_period_end = False
        subscription.status = SubscriptionStatus.ACTIVE
        subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
        
        return subscription
    
    @classmethod
    def update_subscription_plan(cls, subscription_id, new_plan, subscription_type):
        """
        Update a subscription to a new plan.
        
        Args:
            subscription_id: ID of the subscription to update
            new_plan: The new plan to switch to
            subscription_type: 'artist' or 'venue'
            
        Returns:
            Subscription: The updated subscription object
        """
        subscription_class = ArtistSubscription if subscription_type == 'artist' else VenueSubscription
        
        subscription = subscription_class.objects.get(id=subscription_id)
        subscription.plan = new_plan
        subscription.save(update_fields=['plan', 'updated_at'])
        
        return subscription