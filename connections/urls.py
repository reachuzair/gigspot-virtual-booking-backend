from django.urls import path
from .views import artist_connections, artist_connect, artist_disconnect, send_connection_request

urlpatterns = [
    path('artist/', artist_connections, name='artist_connections'),
    path('artist/connect/', artist_connect, name='artist_connect'),
    path('artist/disconnect/', artist_disconnect, name='artist_disconnect'),
    path('artist/send_connection_request/', send_connection_request, name='send_connection_request'),
]