from .views import fan_ticket_list, featured_artists_view
from django.urls import path
urlpatterns = [
    path('tickets/', fan_ticket_list, name='fan_ticket_list'),
    path('featured-artists/', featured_artists_view, name='featured_artists'),
    path('featured-artists/<int:id>/', featured_artists_view,
         name='featured_artist_detail'),
]
