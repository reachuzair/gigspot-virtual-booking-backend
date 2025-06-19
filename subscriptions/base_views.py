"""Base views for subscription management."""
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import Http404
from django.utils import timezone
from django.db import transaction
import logging
from .models import ArtistSubscription, VenueSubscription, SubscriptionPlan, VenueAdPlan
from .services import PlanService, SubscriptionService


class BaseSubscriptionView(APIView):
    """
    Base view for subscription management.
    Handles common subscription operations for both artist and venue subscriptions.
    """
    permission_classes = [IsAuthenticated]
    plan_model = None
    subscription_model = None
    profile_relation = None
    subscription_type = None

    def get_plan(self, plan_id):
        """
        Retrieve a plan by ID from Stripe.
        The plan_id should be the Stripe Price ID.
        """
        import stripe
        from django.conf import settings
        import logging
        
        logger = logging.getLogger(__name__)
        stripe.api_key = settings.STRIPE_SECRET_KEY
        
        logger.debug("Fetching plan from Stripe", {
            'plan_id': plan_id,
            'subscription_type': getattr(self, 'subscription_type', 'unknown')
        })
        
        try:
            # First try to get the price
            price = stripe.Price.retrieve(plan_id)
            if not price or not price.active:
                logger.error("Price not found or inactive in Stripe", {'plan_id': plan_id})
                raise Http404("Plan not found or inactive")
                
            # Then get the product details
            product = stripe.Product.retrieve(price.product)
            
            logger.debug("Retrieved plan from Stripe", {
                'price_id': price.id,
                'product_id': product.id,
                'product_name': product.name,
                'active': price.active,
                'currency': price.currency,
                'unit_amount': price.unit_amount,
                'interval': getattr(price.recurring, 'interval', None) if hasattr(price, 'recurring') else None
            })
            
            # Create a simple object to hold the plan data
            class PlanObject:
                def __init__(self, price, product):
                    self.id = price.id
                    self.stripe_price_id = price.id
                    self.name = product.name
                    self.description = product.description or ''
                    self.price = price.unit_amount / 100 if price.unit_amount else 0
                    self.currency = price.currency.upper()
                    self.interval = getattr(price.recurring, 'interval', 'one_time') if hasattr(price, 'recurring') else 'one_time'
                    self.metadata = dict(price.metadata) if hasattr(price, 'metadata') else {}
                    self.product = product
            
            return PlanObject(price, product)
            
        except stripe.error.InvalidRequestError as e:
            logger.error("Invalid Stripe request", {
                'error': str(e),
                'plan_id': plan_id,
                'error_type': type(e).__name__
            })
            raise Http404("Invalid plan ID")
        except stripe.error.StripeError as e:
            logger.error("Stripe error fetching plan", {
                'error': str(e),
                'plan_id': plan_id,
                'error_type': type(e).__name__
            })
            raise Http404("Error fetching plan from payment processor")

    def get_subscription(self, profile):
        """Retrieve active subscription for a profile if it exists."""
        try:
            return self.subscription_model.objects.get(
                **{self.profile_relation: profile},
                status='active'
            )
        except self.subscription_model.DoesNotExist:
            return None

    def get_profile(self, user):
        """Retrieve the user's profile (artist or venue)."""
        return getattr(user, self.user_profile_attr, None)

    def post(self, request):
        """Handle subscription creation request."""
        from django.conf import settings
        import stripe
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            logger.info("Subscription creation request received", {
                'user': request.user.id if request.user.is_authenticated else 'anonymous',
                'data_received': request.data,
                'content_type': request.content_type,
                'method': request.method,
                'path': request.path
            })
            
            stripe.api_key = settings.STRIPE_SECRET_KEY
            
            # Log request headers for debugging
            logger.debug("Request headers: %s", dict(request.headers))
            
            # Check authentication
            if not request.user.is_authenticated:
                logger.warning("Unauthenticated subscription attempt")
                return self._error_response("Authentication required", status.HTTP_401_UNAUTHORIZED)
            
            # Get and validate profile
            profile = self.get_profile(request.user)
            if not profile:
                logger.error("User profile not found", {
                    'user_id': request.user.id,
                    'profile_attr': getattr(self, 'user_profile_attr', 'Not set')
                })
                return self._error_response("User profile not found")
            
            # Get and validate request data
            plan_id = request.data.get('plan_id')
            payment_method_id = request.data.get('payment_method_id')
            
            logger.debug("Validating request data", {
                'plan_id': plan_id,
                'has_payment_method': bool(payment_method_id)
            })
            
            if not plan_id:
                logger.warning("Missing plan_id in request")
                return self._error_response("Plan ID is required")
                
            if not payment_method_id:
                logger.warning("Missing payment_method_id in request")
                return self._error_response("Payment method is required")
            
            # Get plan
            try:
                plan = self.get_plan(plan_id)
                logger.debug("Plan found", {
                    'plan_id': plan.id if plan else None,
                    'plan_type': type(plan).__name__ if plan else None
                })
            except Http404 as e:
                logger.error("Plan not found", {
                    'plan_id': plan_id,
                    'error': str(e)
                })
                return self._error_response("Invalid plan")
            
            # Create subscription using the service
            try:
                logger.info("Creating subscription with service", {
                    'user_id': request.user.id,
                    'plan_id': plan.id,
                    'subscription_type': getattr(self, 'subscription_type', 'unknown')
                })
                
                subscription, client_secret = SubscriptionService.create_subscription(
                    user=request.user,
                    plan=plan,
                    subscription_type=self.subscription_type,
                    payment_method_id=payment_method_id
                )
                
                logger.info("Subscription created successfully", {
                    'subscription_id': str(subscription.id) if subscription else None,
                    'has_client_secret': bool(client_secret)
                })
                
                return Response({
                    'subscription_id': str(subscription.id),
                    'client_secret': client_secret,
                    'status': 'requires_payment_method' if not client_secret else 'requires_action',
                    'message': 'Subscription created successfully',
                    'subscription': {
                        'id': str(subscription.id),
                        'status': subscription.status,
                        'plan': {
                            'id': str(plan.id),
                            'name': self._get_plan_name(plan),
                            'price': str(plan.price if hasattr(plan, 'price') else getattr(plan, 'monthly_price', 'N/A'))
                        },
                        'current_period_end': (
                            subscription.current_period_end.isoformat() 
                            if subscription.current_period_end 
                            else None
                        ),
                    }
                })
                
            except stripe.error.CardError as e:
                logger.error("Card error in subscription", {
                    'error': str(e),
                    'user_message': str(e.user_message) if hasattr(e, 'user_message') else None,
                    'code': getattr(e, 'code', None),
                    'decline_code': getattr(e, 'decline_code', None)
                })
                return self._error_response(
                    str(e.user_message) if hasattr(e, 'user_message') else 'Your card was declined',
                    status.HTTP_402_PAYMENT_REQUIRED
                )
                
            except stripe.error.StripeError as e:
                logger.error("Stripe error in subscription", {
                    'error': str(e),
                    'type': type(e).__name__,
                    'http_status': getattr(e, 'http_status', None),
                    'json_body': getattr(e, 'json_body', None)
                })
                return self._error_response(
                    "Payment processing error. Please try again.",
                    status.HTTP_500_INTERNAL_SERVER_ERROR
                )
                
        except Http404 as e:
            logger.error("Resource not found in subscription", {
                'error': str(e),
                'path': request.path
            })
            return self._error_response("The requested resource was not found.", status.HTTP_404_NOT_FOUND)
            
        except Exception as e:
            logger.exception("Unexpected error in subscription creation", {
                'error': str(e),
                'type': type(e).__name__,
                'user': request.user.id if request.user.is_authenticated else 'anonymous',
                'path': request.path
            })
            return self._error_response(
                "An unexpected error occurred while processing your request.",
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request):
        """Handle subscription cancellation request."""
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return self._error_response("No active subscription found", status.HTTP_404_NOT_FOUND)

        try:
            subscription.cancel_at_period_end = True
            subscription.status = 'canceled'
            subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
            return Response({"status": "subscription_will_cancel"})
        except Exception as e:
            return self._error_response(str(e))

    def get(self, request):
        """Retrieve current subscription details."""
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return Response({"status": "no_subscription"})

        return self._subscription_details(subscription)

    def _error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        """Helper method for error responses."""
        return Response({"error": message}, status=status_code)

    def _get_plan_name(self, plan):
        """Get the display name of a plan based on its type."""
        if hasattr(plan, 'get_subscription_tier_display'):  # For SubscriptionPlan
            return plan.get_subscription_tier_display()
        elif hasattr(plan, 'get_name_display'):  # For VenueAdPlan
            return plan.get_name_display()
        return str(plan.id)
        
    def _subscription_creation_response(self, plan):
        """Prepare subscription creation response."""
        return Response({
            "plan_id": str(plan.id),
            "plan_name": self._get_plan_name(plan),
            "price": str(plan.price if hasattr(plan, 'price') else plan.monthly_price),
            "subscription_type": self.subscription_type,
            "next_step": "process_payment"
        })

    def _subscription_details(self, subscription):
        """Prepare subscription details response."""
        plan = subscription.plan
        return Response({
            "status": subscription.status,
            "plan": {
                "id": str(plan.id),
                "name": self._get_plan_name(plan),
                "price": str(plan.price if hasattr(plan, 'price') else plan.monthly_price),
                "billing_interval": getattr(plan, 'billing_interval', 'month')
            },
            "current_period_end": (
                subscription.current_period_end.isoformat() 
                if subscription.current_period_end 
                else None
            ),
            "cancel_at_period_end": getattr(subscription, 'cancel_at_period_end', False)
        })