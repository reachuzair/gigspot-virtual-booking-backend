# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    subscription_plans,
    create_artist_subscription,
    manage_artist_subscription,
    payment_methods,
    test_create_artist_subscription,
    VenueAdPlanViewSet,
    VenueSubscriptionViewSet,
    get_venue_subscription_status
)
# from .webhooks import stripe_webhook

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'venue/plans', VenueAdPlanViewSet, basename='venue-plan')
router.register(r'venue/subscriptions', VenueSubscriptionViewSet, basename='venue-subscription')

urlpatterns = [
    # Artist subscription endpoints
    path('plans/', subscription_plans, name='subscription-plans'),
    path('create/', create_artist_subscription, name='create-subscription'),
    path('test-create/', test_create_artist_subscription, name='test-create-subscription'),
    path('manage/', manage_artist_subscription, name='manage-subscription'),
    path('payment-methods/', payment_methods, name='payment-methods'),
    
    # Venue subscription endpoints
    path('', include(router.urls)),
    path('venue/<int:venue_id>/status/', get_venue_subscription_status, name='venue-subscription-status'),
    
    # Webhooks
    # path('stripe/webhook/', stripe_webhook, name='stripe-webhook'),
]