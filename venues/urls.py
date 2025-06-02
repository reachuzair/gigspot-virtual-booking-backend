
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    LikeEventView,
    UserLikedEventsView,
    VenueListView,
    EventListCreateView,
    EventDetailView,
    UpcomingEventsView
)

# Create a router for API endpoints
router = DefaultRouter()

urlpatterns = [
    
    path('venues/', VenueListView.as_view(), name='venue-list'),
    path('events/', EventListCreateView.as_view(), name='event-list'),
    path('events/upcoming/', UpcomingEventsView.as_view(), name='upcoming-events'),
    path('events/<int:pk>/', EventDetailView.as_view(), name='event-detail'),
    path('events/<int:event_id>/like/', LikeEventView.as_view(), name='event-like'),
    path('events/likes/', UserLikedEventsView.as_view(), name='user-liked-events'),
]

urlpatterns += router.urls
