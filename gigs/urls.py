from django.urls import path
from .views import get_gigs, get_gig, create_gig

urlpatterns = [
    path('', get_gigs, name='get_gigs'),
    path('<int:id>/', get_gig, name='get_gig'),
    path('create/', create_gig, name='create_gig')
]