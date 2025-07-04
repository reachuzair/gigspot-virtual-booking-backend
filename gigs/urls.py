from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    GigByCityView, artist_event_history, get_contract_by_gig, list_gigs, GigDetailView, LikeGigView, UserLikedGigsView, UpcomingGigsView, my_requests, pending_venue_gigs,
    send_invite_request, accept_invite_request, reject_invite_request,
    initiate_gig, add_gig_type, add_gig_details, signed_events, submitted_requests, update_gig_status,
    generate_contract, get_contract, sign_contract, generate_contract_pin,
    create_venue_event, add_gig_venue_fee, validate_ticket_price, TourViewSet
)
# Import tour views lazily to prevent circular imports
from . import TourVenueSuggestionsAPI, BookedVenuesAPI

# Create a router for ViewSets
router = DefaultRouter()
router.register(r'tours', TourViewSet, basename='tour')

# Gig URL patterns
gig_urls = [
    # Gig listing and details
    path('', list_gigs, name='list_gigs'),
    path('upcoming/', UpcomingGigsView.as_view(), name='upcoming_gigs'),
    path('upcoming/<int:artist_id>/', UpcomingGigsView.as_view(), name='artist_upcoming_gigs'),
    path('<int:id>/', GigDetailView.as_view(), name='gig_detail'),
    path('event-history/', artist_event_history, name='event_history'),
    path('sign-contract/<int:contract_id>/', sign_contract, name='sign_contract'),

    # Gig actions
    path('initiate/', initiate_gig, name='initiate_gig'),
    path('<int:id>/like/', LikeGigView.as_view(), name='like_gig'),
    path('liked/', UserLikedGigsView.as_view(), name='user_liked_gigs'),
    path('validate-price/', validate_ticket_price, name='validate_ticket_price'),

    # Contract related
    path('contract/generate-pin/', generate_contract_pin,
         name='generate_contract_pin'),
    path('<int:gig_id>/contract/generate/',
         generate_contract, name='generate_contract'),
    path('contract/<int:contract_id>/', get_contract, name='get_contract'),
    path('contract/gig/<int:gig_id>/', get_contract_by_gig, name='get_contract_by_gig_artist'),

    # Gig management
    path('<int:id>/type/', add_gig_type, name='add_gig_type'),
    path('<int:id>/add-details/', add_gig_details, name='add_gig_details'),
    path('<int:id>/status/', update_gig_status, name='update_gig_status'),
    path('<int:id>/venue-fee/', add_gig_venue_fee, name='add_gig_venue_fee'),
    path('pending-gigs/', pending_venue_gigs, name='pending_venue_gigs'),

    # Invitations
    path('<int:id>/invite/', send_invite_request, name='send_invite_request'),
    path('<int:id>/accept-invite/', accept_invite_request,
         name='accept_invite_request'),
    path('<int:id>/reject-invite/', reject_invite_request,
         name='reject_invite_request'),

    # Venue-specific endpoints
    path('venue/events/create/', create_venue_event, name='create_venue_event'),
    
    # Gig filtering and requests
    path('by-city/', GigByCityView.as_view(), name='list_gigs_by_city'),
    path('requests/submitted/', submitted_requests, name='submitted-requests'),
    path('requests/received/', my_requests, name='my-requests'),
    path('events/signed/', signed_events, name='signed-events'),
    path('events/signed/<int:contract_id>/', signed_events, name='signed-events-artist'),
]

# Tour URL patterns
tour_urls = [
    # Include ViewSet URLs
    path('', include(router.urls)),
    
    # Custom tour endpoints
    path('tours/<int:tour_id>/suggest-venues/', 
         TourVenueSuggestionsAPI().as_view(), 
         name='suggest-venues'),
    path('tours/<int:tour_id>/booked-venues/', 
         BookedVenuesAPI().as_view(), 
         name='booked-venues'),
]

# Combine all URL patterns
urlpatterns = gig_urls + tour_urls
