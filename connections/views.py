from rest_framework import status, permissions
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from custom_auth.models import Artist
from django.shortcuts import get_object_or_404

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def artist_connections(request):
    """
    List all connections for the authenticated artist.
    """
    try:
        artist = Artist.objects.get(user=request.user)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    connections = artist.connections.all()
    data = [
        {
            'id': conn.id,
            'band_name': conn.band_name,
            'user_id': conn.user.id,
            'state': conn.state,
            'performance_tier': conn.performance_tier,
            'subscription_tier': conn.subscription_tier,
        }
        for conn in connections
    ]
    return Response({'connections': data}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def artist_connect(request):
    """
    Connect to another artist.
    """
    try:
        artist = Artist.objects.get(user=request.user)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    target_id = request.data.get('artist_id')
    if not target_id:
        return Response({'detail': 'artist_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
    target_artist = get_object_or_404(Artist, id=target_id)
    if target_artist == artist:
        return Response({'detail': 'Cannot connect to yourself.'}, status=status.HTTP_400_BAD_REQUEST)

    artist.connections.add(target_artist)
    return Response({'detail': 'Connection added.'}, status=status.HTTP_201_CREATED)

