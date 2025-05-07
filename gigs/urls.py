from django.urls import path
from .views import (
    get_gigs, 
    get_gig, 
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
    )

urlpatterns = [
    path('', get_gigs, name='get_gigs'),
    path('list/', list_gigs, name='list_gigs'),
    path('<int:id>/', get_gig, name='get_gig'),
    path('contract/generate-pin/', generate_contract_pin, name='generate_contract_pin'),
    path('<int:gig_id>/contract/generate/', generate_contract, name='generate_contract'),
    path('contract/<int:contract_id>/', get_contract, name='get_contract'),
    path('<int:id>/type/', add_gig_type, name='add_gig_type'),
    path('initiate/', initiate_gig, name='initiate_gig'),
    path('<int:id>/add-details/', add_gig_details, name='add_gig_details'),
    path('<int:id>/status/', update_gig_status, name='update_gig_status'),
    path('<int:id>/accept-invite/', accept_invite_request, name='accept_invite_request'),
    path('<int:id>/reject-invite/', reject_invite_request, name='reject_invite_request'),
    path('<int:id>/invite/', send_invite_request, name='send_invite_request')
]