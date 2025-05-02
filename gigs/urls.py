from django.urls import path
from .views import (
    get_gigs, 
    get_gig, 
    create_gig, 
    update_gig, 
    generate_contract_pin,
    generate_contract,
    get_contract
    )

urlpatterns = [
    path('', get_gigs, name='get_gigs'),
    path('<int:id>/', get_gig, name='get_gig'),
    path('create/', create_gig, name='create_gig'),
    path('update/<int:id>/', update_gig, name='update_gig'),
    path('contract/generate-pin/', generate_contract_pin, name='generate_contract_pin'),
    path('contract/generate/', generate_contract, name='generate_contract'),
    path('contract/<int:contract_id>/', get_contract, name='get_contract')
]