
from django.urls import path
from .views import VenueListView

urlpatterns = [
    path('venues/', VenueListView.as_view(), name='venue-list'),
]
