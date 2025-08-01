from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from custom_auth.models import Artist, PerformanceTier, Venue
from gigs.models import Gig, Status
from gigs.serializers import GigSerializer
from .serializers import  ArtistAnalyticsSerializer, ArtistSerializer
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q

import math

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
    gig_id = request.query_params.get('gig_id')  # Get gig_id from query params

    if search_query:
        queryset = Artist.objects.select_related('user').filter(
            Q(band_name__icontains=search_query) |
            Q(user__name__icontains=search_query) |
            Q(user__email__icontains=search_query)
        )
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

    # Pagination
    class CustomPagination(PageNumberPagination):
        page_size_query_param = 'page_size'
        max_page_size = 100
        page_size = 10

    paginator = CustomPagination()
    paginated_artists = paginator.paginate_queryset(sorted_artists, request)

    # Pass gig_id to serializer context
    serializer = ArtistSerializer(paginated_artists, many=True, context={
        'request': request
    })

    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_artist(request, user_id):
    try:
        artist = Artist.objects.get(user_id=user_id)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ArtistSerializer(artist, context={'request': request})
    return Response(serializer.data)


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
                    {'detail': 'No artist profile found for this user'},
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
                    {'detail': 'You do not have permission to view this artist\'s analytics'},
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
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_nearby_events(request):
    user = request.user

    # Ensure only artists are allowed
    if user.role != 'artist':
        return Response(
            {"detail": "Only artists can access nearby events."},
            status=status.HTTP_403_FORBIDDEN
        )

    try:
        artist = Artist.objects.get(user=user)
        city = artist.city
        state = artist.state
    except Artist.DoesNotExist:
        return Response(
            {"detail": "Artist profile not found."},
            status=status.HTTP_404_NOT_FOUND
        )

    if not city or not state:
        return Response(
            {"detail": "Your artist profile is missing city/state."},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Filter gigs based on matching venue city/state
    gigs = Gig.objects.filter(
        status=Status.APPROVED,
        is_public=True,
        venue__city__iexact=city.strip(),
        venue__state__iexact=state.strip()
    ).select_related('venue')

    serializer = GigSerializer(gigs, many=True, context={'request': request})
    return Response({'results': serializer.data})


class ArtistMerchView(APIView):
    permission_classes = [IsAuthenticated]

    def get_artist(self, user):
        artist = getattr(user, 'artist_profile', None)
        if not artist:
            return None, Response({'detail': 'Only artists can access this endpoint.'}, status=status.HTTP_403_FORBIDDEN)
        subscription = getattr(artist, 'subscription', None)
        if not subscription or subscription.plan.subscription_tier.upper() != 'PREMIUM':
            return None, Response({'detail': 'Premium subscription required.'}, status=status.HTTP_403_FORBIDDEN)

        return artist, None

    def get(self, request):
        artist, error = self.get_artist(request.user)
        if error:
            return error
        return Response({'merch_url': artist.merch_url}, status=status.HTTP_200_OK)

    def post(self, request):
        artist, error = self.get_artist(request.user)
        if error:
            return error

        merch_url = request.data.get('merch_url')
        if not merch_url:
            return Response({'detail': 'Merch URL is required.'}, status=status.HTTP_400_BAD_REQUEST)

        artist.merch_url = merch_url
        artist.save()
        return Response({'detail': 'Merch URL saved successfully.'}, status=status.HTTP_200_OK)



