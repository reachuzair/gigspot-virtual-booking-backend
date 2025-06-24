from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from custom_auth.models import Artist, PerformanceTier
from .serializers import ArtistSerializer, ArtistAnalyticsSerializer
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

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
    search_query = request.query_params.get('search', '')
    if search_query:
        queryset = Artist.objects.select_related('user').filter(Q(band_name__icontains=search_query) | Q(user__name__icontains=search_query) | Q(user__email__icontains=search_query))
    else:
        queryset = Artist.objects.select_related('user').all()
    # Exclude the requesting artist
    queryset = queryset.exclude(user=user)

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
    try:
        artist = Artist.objects.get(id=artist_id)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found.'}, status=status.HTTP_404_NOT_FOUND)

    artist_serializer = ArtistSerializer(artist)
    response_data = artist_serializer.data
    return Response(response_data)

class ArtistAnalyticsView(APIView):
    """
    API endpoint to get artist analytics including fan engagement,
    social media following, playlist views, and buzz score percentage.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, artist_id=None):
        # If no artist_id is provided, use the current user's artist profile
        if artist_id is None:
            if not hasattr(request.user, 'artist_profile'):
                return Response(
                    {'error': 'No artist profile found for this user'},
                    status=status.HTTP_404_NOT_FOUND
                )
            artist = request.user.artist_profile
        else:
            # Only allow artists to view their own analytics or admins to view any
            if not request.user.is_staff and (
                not hasattr(request.user, 'artist_profile') or 
                request.user.artist_profile.id != artist_id
            ):
                return Response(
                    {'error': 'You do not have permission to view this artist\'s analytics'},
                    status=status.HTTP_403_FORBIDDEN
                )
            artist = get_object_or_404(Artist, id=artist_id)
        
        # Update the artist's metrics from SoundCharts if needed
        # This is optional - you can remove this block if you want to use cached values only
        try:
            from services.soundcharts import SoundChartsAPI
            soundcharts = SoundChartsAPI()
            if hasattr(soundcharts, 'update_artist_metrics'):
                soundcharts.update_artist_metrics(artist)
        except Exception as e:
            # Log the error but continue with the request
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to update artist metrics: {str(e)}")
        
        # Serialize and return the data
        serializer = ArtistAnalyticsSerializer(artist)
        return Response(serializer.data)