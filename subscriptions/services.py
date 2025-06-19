"""Services for handling subscription-related operations."""
import logging
from django.utils import timezone
from datetime import datetime, timezone
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
    def create_stripe_customer(cls, user, payment_method_id, subscription_type):
        """
        Create or retrieve a Stripe customer for the user.
        
        Args:
            user: The user to create/retrieve customer for
            payment_method_id: Stripe payment method ID
            subscription_type: Type of subscription ('artist' or 'venue')
            
        Returns:
            stripe.Customer: The Stripe customer object
            
        Raises:
            stripe.error.StripeError: If there's an error with Stripe API
        """
        from django.conf import settings
        import stripe
        import logging
        
        logger = logging.getLogger(__name__)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        # Get the appropriate subscription model and field names based on type
        if subscription_type == 'artist':
            subscription_class = ArtistSubscription
            profile_relation = 'artist'  # Matches the OneToOneField name in ArtistSubscription
            profile_attr = 'artist_profile'  # Attribute name on the User model
        else:
            subscription_class = VenueSubscription
            profile_relation = 'venue'  # Matches the ForeignKey name in VenueSubscription
            profile_attr = 'venue_profile'  # Attribute name on the User model
        
        # Try to get existing subscription
        try:
            profile = getattr(user, profile_attr, None)
            if not profile:
                raise ValueError(f"User does not have a {profile_attr}")
                
            # Use the correct field name for the filter
            subscription = subscription_class.objects.filter(**{profile_relation: profile}).first()
            
            # If subscription exists and has a customer ID, retrieve it
            if subscription and subscription.stripe_customer_id:
                logger.debug("Retrieving existing Stripe customer", {
                    'stripe_customer_id': subscription.stripe_customer_id,
                    'subscription_type': subscription_type,
                    'user_id': user.id
                })
                
                customer = stripe.Customer.retrieve(subscription.stripe_customer_id)
                
                # Attach payment method if provided
                if payment_method_id:
                    logger.debug("Attaching payment method to existing customer", {
                        'customer_id': customer.id,
                        'payment_method_id': payment_method_id
                    })
                    try:
                        payment_method = stripe.PaymentMethod.attach(
                            payment_method_id,
                            customer=customer.id,
                        )
                        # Set as default payment method
                        stripe.Customer.modify(
                            customer.id,
                            invoice_settings={
                                'default_payment_method': payment_method.id,
                            },
                        )
                        logger.debug("Successfully attached payment method", {
                            'customer_id': customer.id,
                            'payment_method_id': payment_method.id
                        })
                    except stripe.error.StripeError as e:
                        logger.error("Failed to attach payment method", {
                            'error': str(e),
                            'type': type(e).__name__,
                            'customer_id': customer.id,
                            'payment_method_id': payment_method_id
                        })
                        raise
                
                return customer
                
        except stripe.error.StripeError as e:
            logger.warning("Failed to retrieve existing Stripe customer, will create new one", {
                'error': str(e),
                'type': type(e).__name__,
                'subscription_type': subscription_type,
                'user_id': user.id
            })
        
        # Create new customer
        customer = stripe.Customer.create(
            email=user.email,
            payment_method=payment_method_id,
            invoice_settings={
                'default_payment_method': payment_method_id,
            },
            metadata={
                'user_id': user.id,
                'user_type': subscription_type
            }
        )
        
        logger.info("Created new Stripe customer", {
            'customer_id': customer.id,
            'subscription_type': subscription_type,
            'user_id': user.id
        })
        
        return customer
    
    @classmethod
    def create_subscription(cls, user, plan, subscription_type, payment_method_id=None):
        """
        Create a new subscription for the user.
        
        Args:
            user: The user to create the subscription for
            plan: The plan to subscribe to (must have stripe_price_id attribute)
            subscription_type: Type of subscription ('artist' or 'venue')
            payment_method_id: Optional Stripe payment method ID
            
        Returns:
            tuple: (subscription_record, client_secret)
        """
        from django.conf import settings
        import stripe
        import logging
        from .models import SubscriptionPlan
        
        logger = logging.getLogger(__name__)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        if not hasattr(plan, 'stripe_price_id') or not plan.stripe_price_id:
            raise ValueError("Plan must have a stripe_price_id")
            
        # Create or retrieve Stripe customer
        customer = cls.create_stripe_customer(user, payment_method_id, subscription_type)
        
        try:
            # Create Stripe subscription
            subscription = stripe.Subscription.create(
                customer=customer.id,
                items=[{
                    'price': plan.stripe_price_id,
                }],
                payment_behavior='default_incomplete',
                payment_settings={'save_default_payment_method': 'on_subscription'},
                expand=['latest_invoice.payment_intent'],
            )
            
            logger.info("Created Stripe subscription", {
                'subscription_id': subscription.id,
                'customer_id': customer.id,
                'plan_id': plan.stripe_price_id,
                'subscription_type': subscription_type,
                'user_id': user.id
            })
            
            # Create or update local subscription record
            with transaction.atomic():
                subscription_class = ArtistSubscription if subscription_type == 'artist' else VenueSubscription
                profile_relation = 'artist' if subscription_type == 'artist' else 'venue'
                profile_attr = 'artist_profile' if subscription_type == 'artist' else 'venue_profile'
            
                # Get the profile (artist or venue) for the user
                profile = getattr(user, profile_attr, None)
                if not profile:
                    raise ValueError(f"User does not have a {profile_attr}")
                
                # Get or create the actual SubscriptionPlan from the database
                if hasattr(plan, '_meta') and plan._meta.model_name == 'subscriptionplan':
                    # If plan is already a SubscriptionPlan instance, use it
                    subscription_plan = plan
                else:
                    # Otherwise, find or create a SubscriptionPlan
                    subscription_plan, _ = SubscriptionPlan.objects.get_or_create(
                        stripe_price_id=plan.stripe_price_id,
                        defaults={
                            'subscription_tier': 'FREE' if 'free' in plan.name.lower() else 'PREMIUM',
                            'price': plan.price,
                            'billing_interval': plan.interval,
                            'features': {}
                        }
                    )
                    
                # Create the subscription record with the profile and customer ID
                subscription_data = {
                    'plan': subscription_plan,
                    'stripe_customer_id': customer.id,
                    'stripe_subscription_id': subscription.id,
                    'status': SubscriptionStatus.ACTIVE,
                    'current_period_end': datetime.fromtimestamp(subscription.current_period_end, tz=timezone.utc),
                    'cancel_at_period_end': subscription.cancel_at_period_end,
                }          
            # Use the correct field name for the subscription model
            if subscription_type == 'artist':
                subscription_record, created = subscription_class.objects.update_or_create(
                    artist=profile,
                    defaults=subscription_data
                )
            else:
                subscription_record, created = subscription_class.objects.update_or_create(
                    venue=profile,
                    defaults=subscription_data
                )
            
            client_secret = subscription.latest_invoice.payment_intent.client_secret if hasattr(subscription.latest_invoice.payment_intent, 'client_secret') else None
            
            return subscription_record, client_secret
            
        except stripe.error.StripeError as e:
            # Log the error for debugging
            import logging
            logger.error(f"Stripe error creating subscription: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Error creating subscription: {str(e)}")
            raise
    
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