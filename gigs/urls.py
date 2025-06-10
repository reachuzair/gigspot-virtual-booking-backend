from django.urls import path
from .views import (
    get_gigs, 
    GigDetailView,
    list_gigs,
    generate_contract_pin,
    generate_contract,
    get_contract,
    add_gig_type,
    initiate_gig,
    add_gig_details,
    update_gig_status,
    send_invite_request,
    accept_invite_request,
    reject_invite_request,
    add_gig_venue_fee,
    create_venue_event,
    LikeGigView,
    UserLikedGigsView,
    UpcomingGigsView,
)

urlpatterns = [
    # Gig listing and details
    path('', get_gigs, name='get_gigs'),
    path('list/', list_gigs, name='list_gigs'),
    path('upcoming/', UpcomingGigsView.as_view(), name='upcoming_gigs'),
    path('<int:id>/', GigDetailView.as_view(), name='gig_detail'),
    
    # Gig actions
    path('initiate/', initiate_gig, name='initiate_gig'),
    path('<int:id>/like/', LikeGigView.as_view(), name='like_gig'),
    path('liked/', UserLikedGigsView.as_view(), name='user_liked_gigs'),
    
    # Contract related
    path('contract/generate-pin/', generate_contract_pin, name='generate_contract_pin'),
    path('<int:gig_id>/contract/generate/', generate_contract, name='generate_contract'),
    path('contract/<int:contract_id>/', get_contract, name='get_contract'),
    
    # Gig management
    path('<int:id>/type/', add_gig_type, name='add_gig_type'),
    path('<int:id>/add-details/', add_gig_details, name='add_gig_details'),
    path('<int:id>/status/', update_gig_status, name='update_gig_status'),
    path('<int:id>/venue-fee/', add_gig_venue_fee, name='add_gig_venue_fee'),
    
    # Invitations
    path('<int:id>/invite/', send_invite_request, name='send_invite_request'),
    path('<int:id>/accept-invite/', accept_invite_request, name='accept_invite_request'),
    path('<int:id>/reject-invite/', reject_invite_request, name='reject_invite_request'),
    
    # Venue-specific endpoints
    path('venue/events/create/', create_venue_event, name='create_venue_event'),
]