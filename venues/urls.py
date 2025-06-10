from django.urls import path
from .views import VenueListView, VenueDetailView

app_name = 'venues'

urlpatterns = [
    # List all venues with filtering and search
    path('', VenueListView.as_view(), name='venue-list'),
    
    # Get details for a specific venue
    path('<int:id>/', VenueDetailView.as_view(), name='venue-detail'),
]
