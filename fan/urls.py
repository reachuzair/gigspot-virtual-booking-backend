from .views import fan_ticket_list, featured_artist_with_events_view, featured_artists_view, liked_artists_view, toggle_artist_like
from django.urls import path
urlpatterns = [
    path('tickets/', fan_ticket_list, name='fan_ticket_list'),
    path('featured-artists/', featured_artists_view, name='featured_artists'),
    path('featured-artists/<int:id>/', featured_artists_view,
         name='featured_artist_detail'),
    path('featured-artist-events/<int:id>/', featured_artist_with_events_view),
    path('artists/<int:id>/like/', toggle_artist_like, name='toggle-artist-like'),
    path('liked-artists/', liked_artists_view, name='liked_artists'),

]
