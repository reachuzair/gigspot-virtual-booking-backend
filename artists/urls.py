from django.urls import path
from .views import  list_artists, get_artist

urlpatterns = [
    path('', list_artists, name='list_artists'),
    path('<int:artist_id>/', get_artist, name='get_artist'),
    
]
