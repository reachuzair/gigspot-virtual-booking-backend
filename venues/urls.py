
from django.urls import path
from .views import VenueDetailView, VenueListView

urlpatterns = [
    path('venues/', VenueListView.as_view(), name='venue-list'),
    path('venue/<int:id>/', VenueDetailView.as_view(), name='venue-detail'),
]
