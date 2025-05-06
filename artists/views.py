from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Artist
from .serializers import ArtistSerializer

from rest_framework.pagination import PageNumberPagination
from custom_auth.models import PerformanceTier

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_artists(request):
    user = request.user
    try:
        requesting_artist = Artist.objects.get(user=user)
        user_tier = requesting_artist.performance_tier
    except Artist.DoesNotExist:
        requesting_artist = None
        user_tier = None

    # Exclude the requesting artist
    queryset = Artist.objects.exclude(user=user)

    # Sort: matching performance_tier first, then others
    if user_tier:
        queryset = list(queryset)
        matching = [a for a in queryset if a.performance_tier == user_tier]
        others = [a for a in queryset if a.performance_tier != user_tier]
        sorted_artists = matching + others
    else:
        sorted_artists = list(queryset)

    # Pagination using DRF's PageNumberPagination
    class CustomPagination(PageNumberPagination):
        page_size_query_param = 'page_size'
        max_page_size = 100
        page_size = 10

    paginator = CustomPagination()
    paginated_artists = paginator.paginate_queryset(sorted_artists, request)
    serializer = ArtistSerializer(paginated_artists, many=True)
    return paginator.get_paginated_response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_artist(request, artist_id):
    from gigs.models import Gig
    from gigs.serializers import GigSerializer
    try:
        artist = Artist.objects.get(id=artist_id)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found.'}, status=status.HTTP_404_NOT_FOUND)
    # Serialize artist data
    artist_serializer = ArtistSerializer(artist)
    # Get gigs for this artist
    gigs = Gig.objects.filter(artist=artist)
    gigs_serializer = GigSerializer(gigs, many=True)
    response_data = artist_serializer.data
    response_data['gigs'] = gigs_serializer.data
    return Response(response_data)