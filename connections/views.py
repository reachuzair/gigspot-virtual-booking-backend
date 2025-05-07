from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from custom_auth.models import Artist
from django.shortcuts import get_object_or_404
from .models import Connection

@api_view(['GET'])
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
def send_connection_request(request):
    """
    Send a connection request to another artist.
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
    
    connection = Connection.objects.filter(artist=artist, connected_artist=target_artist, status='pending')
    if connection.exists():
        return Response({'detail': 'Connection request already sent.'}, status=status.HTTP_400_BAD_REQUEST)
    connection = Connection.objects.create(artist=artist, connected_artist=target_artist)
    return Response({'detail': 'Connection request sent.'}, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def accept_connection_request(request):
    """
    Accept a connection request from another artist.
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

    connection = Connection.objects.filter(artist=target_artist, connected_artist=artist, status='pending')
    if not connection.exists():
        return Response({'detail': 'Connection request not found.'}, status=status.HTTP_404_NOT_FOUND)
    connection = connection.first()
    connection.status = 'accepted'
    connection.save()
    artist.connections.add(target_artist)
    target_artist.connections.add(artist)
    return Response({'detail': 'Connection accepted.'}, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def reject_connection_request(request):
    """
    Reject a connection request from another artist.
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

    connection = Connection.objects.filter(artist=target_artist, connected_artist=artist, status='pending')
    if not connection.exists():
        return Response({'detail': 'Connection request not found.'}, status=status.HTTP_404_NOT_FOUND)
    connection = connection.first()
    connection.status = 'rejected'
    connection.save()
    return Response({'detail': 'Connection rejected.'}, status=status.HTTP_201_CREATED)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def artist_disconnect(request):
    """
    Disconnect from another artist.
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
        return Response({'detail': 'Cannot disconnect from yourself.'}, status=status.HTTP_400_BAD_REQUEST)

    artist.connections.remove(target_artist)
    return Response({'detail': 'Connection removed.'}, status=status.HTTP_200_OK)

