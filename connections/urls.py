from django.urls import path
from .views import artist_connections

urlpatterns = [
    path('artist/', artist_connections, name='artist_connections'),
]