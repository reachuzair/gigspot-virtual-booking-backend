from django.urls import path
from .views import (
    get_gigs, 
    get_gig, 
    create_gig, 
    update_gig, 
    update_gig_live_status, 
    get_gig_rows, 
    add_seat_row, 
    get_seats, 
    add_seats,
    delete_seat,
    delete_seat_row,
    generate_contract_pin,
    generate_contract,
    get_contract
    )

urlpatterns = [
    path('', get_gigs, name='get_gigs'),
    path('<int:id>/', get_gig, name='get_gig'),
    path('create/', create_gig, name='create_gig'),
    path('update/<int:id>/', update_gig, name='update_gig'),
    path('update-live-status/<int:id>/', update_gig_live_status, name='update_gig_live_status'),
    path('<int:gig_id>/list-gig-rows/', get_gig_rows, name='get_gig_rows'),
    path('<int:gig_id>/add-gig-row/', add_seat_row, name='add_seat_row'),
    path('<int:gig_id>/list-seats-by-row/<int:row_id>/', get_seats, name='get_seats'),
    path('<int:gig_id>/add-seats-by-row/<int:row_id>/', add_seats, name='add_seats'),
    path('<int:gig_id>/delete-seats/', delete_seat, name='delete_seat'),
    path('<int:gig_id>/delete-row/<int:row_id>/', delete_seat_row, name='delete_seats_by_row'),
    path('contract/generate-pin/', generate_contract_pin, name='generate_contract_pin'),
    path('contract/generate/', generate_contract, name='generate_contract'),
    path('contract/<int:contract_id>/', get_contract, name='get_contract')
]