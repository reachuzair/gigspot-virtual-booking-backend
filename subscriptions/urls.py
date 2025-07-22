"""URL configuration for subscription endpoints."""
from django.urls import path
from .views import (
    PromotionPlansView,
    PromotionPurchaseView,
    SubscriptionPlansView,
    ArtistSubscriptionView,
    VenueSubscriptionView,
    manage_artist_subscription
)

app_name = 'subscriptions'

urlpatterns = [
    # Unified subscription plans (includes both artist and venue plans)
    path('plans/', SubscriptionPlansView.as_view(), name='subscription-plans'),
    
    # Artist subscription management
    path('artists/', ArtistSubscriptionView.as_view(), name='artist-subscription'),
    path('artists/<int:pk>/', ArtistSubscriptionView.as_view(), name='artist-subscription-detail'),
    
    # Venue subscription management
    path('venues/', VenueSubscriptionView.as_view(), name='venue-subscription'),
    path('venues/<int:pk>/', VenueSubscriptionView.as_view(), name='venue-subscription-detail'),
    
    # Legacy endpoint (to be deprecated)
    path('manage-artist-subscription/', manage_artist_subscription, name='manage-artist-subscription'),
    path('venuepromotionplans/', PromotionPlansView.as_view(), name='venue-promotion-plans'),
    path('CreateVenuePromotionPlan/',PromotionPurchaseView.as_view(), name='create-venue-promotion-plan'),
]