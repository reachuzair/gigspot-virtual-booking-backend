"""
Unified views for handling all subscription-related functionality.
Combines endpoints for both artist and venue subscriptions.
"""
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.conf import settings
import stripe
import json

from custom_auth.models import Artist, Venue
from .models import (
    SubscriptionPlan, ArtistSubscription,
    VenueAdPlan, VenueSubscription
)
from .serializers import (
    SubscriptionPlanSerializer, ArtistSubscriptionSerializer,
    VenueAdPlanSerializer, VenueSubscriptionSerializer,
    CreateVenueSubscriptionSerializer, SubscriptionPlanResponseSerializer
)
from .services import SubscriptionService
from .base_views import BaseSubscriptionView

# Initialize Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


class UnifiedSubscriptionPlansView(APIView):
    """
    API endpoint that returns subscription plans for both artists and venues.
    
    This view provides a unified interface to retrieve all available subscription plans
    for both artist and venue accounts, along with the user's current subscription status.
    
    Authentication is required to access this endpoint.
    """
    permission_classes = [IsAuthenticated]
    
    def _get_stripe_plans(self):
        """Fetch all active subscription plans from Stripe"""
        try:
            # Get all active products
            products = stripe.Product.list(active=True, limit=100)
            
            # Get all prices for these products
            prices = stripe.Price.list(active=True, limit=100)
            
            # Organize prices by product
            price_map = {}
            for price in prices.auto_paging_iter():
                if price.product not in price_map:
                    price_map[price.product] = []
                price_map[price.product].append(price)
            
            # Build plan details
            stripe_plans = []
            for product in products.auto_paging_iter():
                product_prices = price_map.get(product.id, [])
                for price in product_prices:
                    interval = price.recurring.interval if hasattr(price, 'recurring') and price.recurring else 'one_time'
                    stripe_plans.append({
                        'id': price.id,
                        'product_id': product.id,
                        'name': product.name,
                        'description': product.description or '',
                        'amount': price.unit_amount / 100 if price.unit_amount else 0,
                        'currency': price.currency.upper(),
                        'interval': interval,
                        'metadata': dict(price.metadata) if hasattr(price, 'metadata') else {}
                    })
            
            return stripe_plans
            
        except stripe.error.StripeError as e:
            print(f"Error fetching Stripe plans: {str(e)}")
            return []
    
    def _ensure_default_venue_plans_exist(self):
        """Ensure default venue plans exist in the database."""
        from .models import VenueAdPlan
        
        default_plans = [
            {
                'name': 'STARTER',
                'description': 'Basic visibility for your venue',
                'monthly_price': 75.00,
                'weekly_price': 25.00,
                'features': {
                    'description': 'Basic visibility for your venue',
                    'features': [
                        'Appear as "Suggested Venue" in artist dashboards',
                        'Appear in city searches',
                        'Basic venue profile visibility'
                    ],
                    'priority_in_search': False,
                    'custom_map_pin': False,
                    'homepage_feature': False,
                    'email_spotlight': False,
                    'analytics_access': False
                }
            },
            {
                'name': 'BOOSTED',
                'description': 'Increased visibility for your venue',
                'monthly_price': 150.00,
                'weekly_price': 37.50,
                'features': {
                    'description': 'Increased visibility for your venue',
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
                    'analytics_access': True
                }
            },
            {
                'name': 'PREMIUM',
                'description': 'Maximum visibility and premium placement',
                'monthly_price': 250.00,
                'weekly_price': 62.50,
                'features': {
                    'description': 'Maximum visibility and premium placement',
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
                    'analytics_access': True
                }
            }
        ]
        
        for plan_data in default_plans:
            VenueAdPlan.objects.update_or_create(
                name=plan_data['name'],
                defaults={
                    'description': plan_data['description'],
                    'monthly_price': plan_data['monthly_price'],
                    'weekly_price': plan_data['weekly_price'],
                    'features': plan_data['features'],
                    'is_active': True
                }
            )
    
    def get(self, request) -> Response:
        """
        Retrieve all active subscription plans for artists and venues with Stripe details.
        
        Returns:
            Response: JSON response containing:
                - artist_plans: List of available artist subscription plans with Stripe details
                - venue_plans: List of available venue ad plans with Stripe details
                - stripe_plans: List of all active Stripe subscription plans
                - has_active_subscription: Object indicating user's subscription status
        """
        try:
            # Ensure default venue plans exist
            self._ensure_default_venue_plans_exist()
            
            # Get Stripe plans
            stripe_plans = self._get_stripe_plans()
            
            # Get only Free and Premium artist plans (case-insensitive match)
            artist_plans = list(SubscriptionPlan.objects.filter(
                is_active=True,
                subscription_tier__in=['FREE', 'PREMIUM']
            ).order_by('price'))
            
            # Get venue plans (Starter, Boosted, Premium)
            venue_plans = list(VenueAdPlan.objects.filter(
                is_active=True,
                name__in=['STARTER', 'BOOSTED', 'PREMIUM']
            ).order_by('monthly_price'))
            
            # Filter out any plans that don't match our expected types
            artist_plans = [p for p in artist_plans if p.subscription_tier.upper() in ['FREE', 'PREMIUM']]
            venue_plans = [p for p in venue_plans if p.name.upper() in ['STARTER', 'BOOSTED', 'PREMIUM']]
            
            # Serialize plans
            artist_plans_serializer = SubscriptionPlanSerializer(artist_plans, many=True)
            venue_plans_serializer = VenueAdPlanSerializer(venue_plans, many=True)
            
            # Check user's subscription status for both artist and venue
            has_active_artist_sub = False
            has_active_venue_sub = False
            
            # Check artist subscription status if user has an artist profile
            if hasattr(request.user, 'artist_profile'):
                subscription = getattr(request.user.artist_profile, 'subscription', None)
                if subscription and subscription.status in ['active', 'trialing']:
                    has_active_artist_sub = True
            
            # Check venue subscription status if user has a venue profile
            if hasattr(request.user, 'venue_profile'):
                subscription = getattr(request.user.venue_profile, 'subscription', None)
                if subscription and subscription.status in ['active', 'trialing']:
                    has_active_venue_sub = True
            
            # Format the response data
            response_data = {
                'artist_plans': artist_plans_serializer.data,
                'venue_plans': venue_plans_serializer.data,
                'stripe_plans': stripe_plans,
                'has_active_subscription': {
                    'artist': has_active_artist_sub,
                    'venue': has_active_venue_sub
                }
            }
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error fetching subscription plans: {str(e)}", exc_info=True)
            
            return Response(
                {'error': 'An error occurred while fetching subscription plans'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _format_artist_plans(self, plans: list) -> list[dict]:
        """Format artist subscription plans for API response."""
        formatted_plans = []
        for plan in plans:
            # Ensure we only include Free and Premium plans
            if plan.subscription_tier.upper() not in ['FREE', 'PREMIUM']:
                continue
                
            formatted_plans.append({
                'id': f'artist_{plan.id}',
                'stripe_price_id': plan.stripe_price_id or '',
                'name': plan.get_subscription_tier_display(),
                'description': plan.features.get('description', ''),
                'price': str(plan.price),
                'billing_interval': plan.billing_interval,
                'features': {
                    'max_shows': plan.features.get('max_shows'),
                    'can_create_tours': plan.features.get('can_create_tours', False),
                    'can_create_shows': plan.features.get('can_create_show', False),
                    'merch_store': plan.features.get('merch_store', False),
                    'analytics': plan.features.get('analytics', 'basic'),
                    'priority_support': plan.features.get('priority_support', False)
                },
                'is_popular': plan.subscription_tier.upper() == 'PREMIUM',
                'is_active': plan.is_active,
                'type': 'artist',
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            })
        return formatted_plans
    
    def _format_venue_plans(self, plans: list) -> list[dict]:
        """Format venue ad plans for API response."""
        formatted_plans = []
        for plan in plans:
            # Ensure we only include Starter, Boosted, and Premium plans
            if plan.name.upper() not in ['STARTER', 'BOOSTED', 'PREMIUM']:
                continue
                
            # Get features, handling both old and new format
            features = plan.features
            if isinstance(features, list):
                # Convert old format to new format
                features = {
                    'priority_in_search': False,
                    'custom_map_pin': False,
                    'homepage_feature': False,
                    'email_spotlight': False,
                    'analytics_access': False,
                    'description': '',
                    'features': features
                }
            
            formatted_plans.append({
                'id': f'venue_{plan.id}',
                'stripe_price_id': plan.monthly_stripe_price_id or '',
                'name': plan.get_name_display(),
                'description': plan.description or features.get('description', ''),
                'price': str(plan.monthly_price),
                'billing_interval': 'month',  # Venue plans are always monthly
                'features': {
                    'priority_in_search': features.get('priority_in_search', False),
                    'custom_map_pin': features.get('custom_map_pin', False),
                    'homepage_feature': features.get('homepage_feature', False),
                    'email_spotlight': features.get('email_spotlight', False),
                    'analytics_access': features.get('analytics_access', False),
                    'description': features.get('description', ''),
                    'features_list': features.get('features', [])
                },
                'is_popular': plan.name.upper() == 'BOOSTED',
                'is_active': plan.is_active,
                'type': 'venue',
                'created_at': plan.created_at.isoformat(),
                'updated_at': plan.updated_at.isoformat()
            })
        return formatted_plans


class ArtistSubscriptionView(BaseSubscriptionView):
    """
    View for managing artist subscriptions.
    """
    model = ArtistSubscription
    serializer_class = ArtistSubscriptionSerializer
    subscription_plan_model = SubscriptionPlan
    user_profile_attr = 'artist_profile'  # Matches User.artist_profile
    profile_relation = 'artist'  # Matches ArtistSubscription.artist field
    subscription_type = 'artist'
    plan_model = SubscriptionPlan
    subscription_model = ArtistSubscription
    
    def get_queryset(self):
        return self.model.objects.filter(artist=self.request.user.artist_profile)
    
    def get_subscription_plan(self, plan_id):
        return get_object_or_404(
            self.subscription_plan_model,
            id=plan_id,
            is_active=True
        )
    
    def create_subscription(self, user, plan, payment_method_id, coupon_code=None):
        """Create a new subscription for an artist."""
        return SubscriptionService.create_artist_subscription(
            user.artist_profile,
            plan,
            payment_method_id,
            coupon_code
        )
    
    def get_active_subscription(self, user):
        """Get the active subscription for an artist."""
        return getattr(user.artist_profile, 'subscription', None)


class VenueSubscriptionView(BaseSubscriptionView):
    """
    View for managing venue subscriptions.
    """
    model = VenueSubscription
    serializer_class = VenueSubscriptionSerializer
    subscription_plan_model = VenueAdPlan
    user_profile_attr = 'venue'  # Matches User.venue (default related_name)
    profile_relation = 'venue'  # Matches VenueSubscription.venue field
    subscription_type = 'venue'
    plan_model = VenueAdPlan
    subscription_model = VenueSubscription
    
    def get_queryset(self):
        return self.model.objects.filter(venue__user=self.request.user)
    
    def get_subscription_plan(self, plan_id):
        return get_object_or_404(
            self.subscription_plan_model,
            id=plan_id,
            is_active=True
        )
    
    def create_subscription(self, user, plan, payment_method_id, coupon_code=None):
        """Create a new subscription for a venue."""
        return SubscriptionService.create_venue_subscription(
            user.venue_profile,
            plan,
            payment_method_id,
            coupon_code
        )
    
    def get_active_subscription(self, user):
        """Get the active subscription for a venue."""
        return getattr(user.venue_profile, 'subscription', None)


class BasePlanView(APIView):
    """Base view for listing subscription plans."""
    permission_classes = [IsAuthenticated]
    model = None
    serializer_class = None
    order_field = None
    
    def get_queryset(self):
        """Return filtered and ordered queryset of active plans."""
        return self.model.objects.filter(is_active=True).order_by(self.order_field)
    
    def get(self, request):
        """Return all active plans."""
        plans = self.get_queryset()
        serializer = self.serializer_class(plans, many=True)
        return Response(serializer.data)


class SubscriptionPlanView(BasePlanView):
    """View for listing subscription plans for artists."""
    model = SubscriptionPlan
    serializer_class = SubscriptionPlanSerializer
    order_field = 'price'


class VenueAdPlanView(BasePlanView):
    """View for listing venue ad plans."""
    model = VenueAdPlan
    serializer_class = VenueAdPlanSerializer
    order_field = 'monthly_price'


def manage_artist_subscription(request):
    """
    View for managing artist subscriptions (create, update, cancel).
    This is a function-based view for compatibility with existing frontend code.
    """
    if not request.user.is_authenticated:
        return Response(
            {'error': 'Authentication required'},
            status=status.HTTP_401_UNAUTHORIZED
        )
    
    try:
        artist = request.user.artist_profile
    except Artist.DoesNotExist:
        return Response(
            {'error': 'Artist profile not found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'POST':
        # Handle subscription creation/update
        payment_method_id = request.data.get('payment_method_id')
        plan_id = request.data.get('plan_id')
        coupon_code = request.data.get('coupon_code')
        
        if not payment_method_id or not plan_id:
            return Response(
                {'error': 'Payment method and plan ID are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {'error': 'Invalid plan ID'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for existing subscription
        subscription = getattr(artist, 'subscription', None)
        
        try:
            if subscription:
                # Update existing subscription
                stripe_sub = SubscriptionService.update_subscription_plan(
                    subscription.stripe_subscription_id,
                    plan.stripe_price_id,
                    coupon_code
                )
                subscription.plan = plan
                subscription.status = stripe_sub.status
                subscription.save()
                
                serializer = ArtistSubscriptionSerializer(subscription)
                return Response(serializer.data)
            else:
                # Create new subscription
                subscription = SubscriptionService.create_artist_subscription(
                    artist,
                    plan,
                    payment_method_id,
                    coupon_code
                )
                serializer = ArtistSubscriptionSerializer(subscription)
                return Response(serializer.data, status=status.HTTP_201_CREATED)
                
        except stripe.error.StripeError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    elif request.method == 'DELETE':
        # Handle subscription cancellation
        subscription = getattr(artist, 'subscription', None)
        if not subscription:
            return Response(
                {'error': 'No active subscription found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            SubscriptionService.cancel_subscription(subscription.stripe_subscription_id)
            subscription.status = 'canceled'
            subscription.canceled_at = timezone.now()
            subscription.save()
            return Response(status=status.HTTP_204_NO_CONTENT)
            
        except stripe.error.StripeError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    return Response(
        {'error': 'Method not allowed'},
        status=status.HTTP_405_METHOD_NOT_ALLOWED
    )