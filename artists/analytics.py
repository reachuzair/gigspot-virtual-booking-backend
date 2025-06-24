from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.utils import timezone
import logging

from custom_auth.models import Artist
from .serializers import ArtistAnalyticsSerializer
from .tasks import update_artist_metrics

logger = logging.getLogger(__name__)


class ArtistAnalyticsView(APIView):
    """
    API endpoint to retrieve artist analytics including:
    - Fan Engagement (%)
    - Social Media Following
    - Playlist Views
    - Buzz Score
    - On Fire Status
    
    This endpoint only returns data from the database and does not make any external API calls.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, artist_id=None):
        """
        Retrieve analytics for the specified artist or the current user's artist profile.
        Only returns data from the database - does not make any external API calls.
        """
        try:
            # Check if user is requesting a specific artist or their own profile
            if artist_id:
                if not request.user.is_staff:
                    return Response(
                        {'error': 'You do not have permission to view this artist\'s analytics'},
                        status=status.HTTP_403_FORBIDDEN
                    )
                artist = get_object_or_404(Artist, id=artist_id)
            else:
                if not hasattr(request.user, 'artist_profile'):
                    return Response(
                        {'error': 'No artist profile found for this user'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                artist = request.user.artist_profile

            # Get the current metrics from the database
            serializer = ArtistAnalyticsSerializer(artist)
            
            # Check if we have any metrics data
            if not artist.last_metrics_update:
                return Response(
                    {'error': 'No analytics data available'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Prepare response data
            response_data = {
                'success': True,
                'data': serializer.data,
                'last_updated': artist.last_metrics_update.isoformat(),
                'metrics_source': 'database'
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in ArtistAnalyticsView: {str(e)}", exc_info=True)
            return Response(
                {'error': 'An error occurred while fetching analytics data'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )