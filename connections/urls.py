from django.urls import path
from .views import artist_connections, artist_connect, artist_disconnect, send_connection_request, accept_connection_request, reject_connection_request

urlpatterns = [
    path('artist/', artist_connections, name='artist_connections'),
    path('artist/connection-accept/', accept_connection_request, name='accept_connection_request'),
    path('artist/connection-reject/', reject_connection_request, name='reject_connection_request'),
    path('artist/disconnect/', artist_disconnect, name='artist_disconnect'),
    path('artist/send_connection_request/', send_connection_request, name='send_connection_request'),
]