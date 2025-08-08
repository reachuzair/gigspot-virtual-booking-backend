"""Base views for subscription management."""
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.http import Http404
from django.utils import timezone
from django.db import transaction
import logging

from custom_auth.models import Artist, Venue

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
    subscription_type = None

    def get_plan(self, plan_id):
        import stripe
        from django.conf import settings
        logger = logging.getLogger(__name__)
        stripe.api_key = settings.STRIPE_SECRET_KEY

        logger.debug("Fetching plan from Stripe", {'plan_id': plan_id, 'subscription_type': self.subscription_type})
        try:
            price = stripe.Price.retrieve(plan_id)
            if not price or not price.active:
                logger.error("Price not found or inactive", {'plan_id': plan_id})
                raise Http404("Plan not found or inactive")

            product = stripe.Product.retrieve(price.product)

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
            logger.error("Invalid Stripe request", {'error': str(e), 'plan_id': plan_id})
            raise Http404("Invalid plan ID")
        except stripe.error.StripeError as e:
            logger.error("Stripe error fetching plan", {'error': str(e), 'plan_id': plan_id})
            raise Http404("Error fetching plan from payment processor")

    def get_profile(self, user):
        """Return the user's artist or venue profile based on their role."""
        try:
            if user.role == 'artist':
                return user.artist_profile
            elif user.role == 'venue':
                return user.venue_profile
        except (Artist.DoesNotExist, Venue.DoesNotExist):
            return None

    def get_subscription(self, profile):
        try:
            return self.subscription_model.objects.get(
                **{self.subscription_type: profile},
                status='active'
            )
        except self.subscription_model.DoesNotExist:
            return None

    def post(self, request):
        from django.conf import settings
        import stripe
        logger = logging.getLogger(__name__)
        logger.info("Subscription creation request received")

        try:
            stripe.api_key = settings.STRIPE_SECRET_KEY

            if not request.user.is_authenticated:
                return self._error_response("Authentication required", status.HTTP_401_UNAUTHORIZED)

            profile = self.get_profile(request.user)
            if not profile:
                logger.error("User profile not found", {'user_id': request.user.id, 'role': request.user.role})
                return self._error_response("User profile not found")

            plan_id = request.data.get('plan_id')
            payment_method_id = request.data.get('payment_method_id')

            if not plan_id:
                return self._error_response("Plan ID is required")
            if not payment_method_id:
                return self._error_response("Payment method is required")

            try:
                plan = self.get_plan(plan_id)
            except Http404:
                return self._error_response("Invalid plan")

            subscription, client_secret = SubscriptionService.create_subscription(
                user=request.user,
                plan=plan,
                subscription_type=self.subscription_type,
                payment_method_id=payment_method_id
            )

            # Save stripe_price_id and current_period_end to artist profile
            if request.user.role == 'artist':
                artist_profile = getattr(request.user, 'artist_profile', None)
                if artist_profile:
                    artist_profile.stripe_price_id = plan.id
                    artist_profile.current_period_end = subscription.current_period_end
                    artist_profile.save(update_fields=['stripe_price_id', 'current_period_end'])
            elif request.user.role == 'venue':
                venue_profile = getattr(request.user, 'venue_profile', None)
                if venue_profile:
                    venue_profile.stripe_price_id = plan.id
                    venue_profile.current_period_end = subscription.current_period_end
                    venue_profile.save(update_fields=['stripe_price_id', 'current_period_end'])

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
                        'price': str(plan.price)
                    },
                    'current_period_end': (
                        subscription.current_period_end.isoformat()
                        if subscription.current_period_end
                        else None
                    ),
                }
            })

        except stripe.error.CardError as e:
            return self._error_response(
                str(e.user_message) if hasattr(e, 'user_message') else 'Your card was declined',
                status.HTTP_402_PAYMENT_REQUIRED
            )

        except stripe.error.StripeError as e:
            return self._error_response("Payment processing error. Please try again.", status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            logger.exception("Unexpected error in subscription creation")
            return self._error_response("An unexpected error occurred while processing your request.", status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request):
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return self._error_response("No active subscription found", status.HTTP_404_NOT_FOUND)

        subscription.cancel_at_period_end = True
        subscription.status = 'canceled'
        subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])
        return Response({"status": "subscription_will_cancel"})

    def get(self, request):
        profile = self.get_profile(request.user)
        if not profile:
            return self._error_response("User profile not found")

        subscription = self.get_subscription(profile)
        if not subscription:
            return Response({"status": "no_subscription"})

        return self._subscription_details(subscription)

    def _error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        return Response({"error": message}, status=status_code)

    def _get_plan_name(self, plan):
        if hasattr(plan, 'get_subscription_tier_display'):
            return plan.get_subscription_tier_display()
        elif hasattr(plan, 'get_name_display'):
            return plan.get_name_display()
        return str(plan.id)

    def _subscription_details(self, subscription):
        plan = subscription.plan
        return Response({
            "status": subscription.status,
            "plan": {
                "id": str(plan.id),
                "name": self._get_plan_name(plan),
                "price": str(plan.price),
                "billing_interval": getattr(plan, 'billing_interval', 'month')
            },
            "current_period_end": (
                subscription.current_period_end.isoformat()
                if subscription.current_period_end
                else None
            ),
            "cancel_at_period_end": getattr(subscription, 'cancel_at_period_end', False)
        })

