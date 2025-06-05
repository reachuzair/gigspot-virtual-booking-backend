from django.urls import path
from .views import VenueListView, VenueDetailView
from .suggested_views import SuggestedVenuesView

app_name = 'venues'

urlpatterns = [
    # List all venues with filtering and search
    path('', VenueListView.as_view(), name='venue-list'),
    # Get suggested venues based on subscription tiers
    path('suggested/', SuggestedVenuesView.as_view(), name='suggested-venues'),
    # Get details for a specific venue
    path('<int:id>/', VenueDetailView.as_view(), name='venue-detail'),
]
