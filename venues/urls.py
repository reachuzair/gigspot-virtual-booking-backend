from django.urls import path
from .views import ArtistBillsAPI, GigDailySalesBreakdownAPI, TicketSalesAPI, VenueListView, VenueDetailView, VenueAnalyticsView, VenueProofUploadView
from .suggested_views import SuggestedVenuesView

app_name = 'venues'

urlpatterns = [
    # List all venues with filtering and search
    path('', VenueListView.as_view(), name='venue-list'),
    # Get suggested venues based on subscription tiers
    path('suggested/', SuggestedVenuesView.as_view(), name='suggested-venues'),
    # Get details for a specific venue
    path('<int:id>/', VenueDetailView.as_view(), name='venue-detail'),
    # Get analytics for the current user's venue shows
    path('analytics/', VenueAnalyticsView.as_view(), name='venue-analytics'),
    path('proofs/', VenueProofUploadView.as_view(), name='venue-proof-list'),
    path('tickets-sales/', TicketSalesAPI.as_view(), name='ticket-sales'),
    path('artist-bills/', ArtistBillsAPI.as_view(), name='artist-bills'),
    path('<int:gig_id>/ticket-sales-breakdown/', GigDailySalesBreakdownAPI.as_view()),
]
