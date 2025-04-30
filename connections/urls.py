from django.urls import path
from .views import artist_connections, artist_connect

urlpatterns = [
    path('artist/', artist_connections, name='artist_connections'),
    path('artist/connect/', artist_connect, name='artist_connect'),
]