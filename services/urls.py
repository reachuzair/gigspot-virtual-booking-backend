from django.urls import path
from .views import search_artist_by_name

urlpatterns = [
    path('search_artist_by_name/', search_artist_by_name, name='search_artist_by_name'),
]