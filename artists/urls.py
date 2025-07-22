from django.urls import path
from . import views

urlpatterns = [
    path('', views.list_artists, name='list_artists'),
    path('<int:user_id>/', views.get_artist, name='get_artist'),
    path('analytics/', views.ArtistAnalyticsView.as_view(), name='artist-analytics'),
    path('analytics/<int:artist_id>/', views.ArtistAnalyticsView.as_view(), name='artist-analytics-detail'),
    path('nearby-events/', views.get_nearby_events, name='nearby_events'),
]