from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import Artist
from artists.serializers import ArtistSerializer
from django.shortcuts import get_object_or_404
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import ROLE_CHOICES
from .serializers import FanTicketSerializer
from gigs.models import Gig
from gigs.serializers import GigDetailSerializer
from payments.models import Ticket



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fan_ticket_list(request):
    user = request.user

    if user.role != ROLE_CHOICES.FAN:
        return Response(
            {"detail": "Only fans can access their tickets."},
            status=status.HTTP_403_FORBIDDEN
        )

    tickets = Ticket.objects.filter(user=user).select_related('gig')
    serializer = FanTicketSerializer(tickets, many=True, context={'request': request})

    return Response({
        "tickets": serializer.data,
        "count": len(serializer.data)
    }, status=status.HTTP_200_OK)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def featured_artists_view(request, id=None):
    if id:
        artist = get_object_or_404(
            Artist, id=id, subscription_tier='PREMIUM')  
        serializer = ArtistSerializer(artist, context={'request': request})
        return Response(serializer.data, status=200)

    artists = Artist.objects.filter(subscription_tier='PREMIUM') 
    serializer = ArtistSerializer(artists, many=True, context={'request': request})
    return Response({"artists": serializer.data}, status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def featured_artist_with_events_view(request, id):
    try:
        artist = get_object_or_404(Artist, id=id, subscription_tier='PREMIUM')

        gigs = Gig.objects.filter(
            Q(created_by=artist.user) | Q(collaborators=artist.user),
            status='approved'
        ).distinct().order_by('-event_date')

        
        artist_data = ArtistSerializer(artist, context={'request': request}).data
        gigs_data = GigDetailSerializer(gigs, many=True, context={'request': request}).data
        artist_data['events'] = gigs_data if gigs.exists() else []

        return Response({
            'artist': artist_data,
        }, status=200)

    except Exception as e:
        return Response({'detail': str(e)}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_artist_like(request, id):
    try:
        user = request.user
        artist = get_object_or_404(Artist, id=id, subscription_tier='PREMIUM')

        if artist.likes.filter(id=user.id).exists():
            artist.likes.remove(user)
            liked = False
        else:
            artist.likes.add(user)
            liked = True

        artist.save()

        return Response({
            'status': 'success',
            'liked': liked,
            'likes_count': artist.likes.count()
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def liked_artists_view(request):
    user = request.user

    if user.role != ROLE_CHOICES.FAN:
        return Response(
            {"detail": "Only fans can access their liked artists."},
            status=status.HTTP_403_FORBIDDEN
        )

    liked_artists = Artist.objects.filter(likes=user).select_related('user')
    serializer = ArtistSerializer(liked_artists, many=True, context={'request': request})

    return Response({
        "liked_artists": serializer.data,
        "count": len(serializer.data)
    }, status=status.HTTP_200_OK)