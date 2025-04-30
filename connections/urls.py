from django.urls import path
from .views import artist_connections, artist_connect, artist_disconnect

urlpatterns = [
    path('artist/', artist_connections, name='artist_connections'),
    path('artist/connect/', artist_connect, name='artist_connect'),
    path('artist/disconnect/', artist_disconnect, name='artist_disconnect'),
]