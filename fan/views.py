from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import Artist, SubscriptionTier
from artists.serializers import ArtistSerializer
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import ROLE_CHOICES
from fan.models import FanTicketSerializer
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
            Artist, id=id, subscription_tier=SubscriptionTier.ELITE)
        serializer = ArtistSerializer(artist, context={'request': request})
        return Response(serializer.data, status=200)

    artists = Artist.objects.filter(subscription_tier=SubscriptionTier.ELITE)
    serializer = ArtistSerializer(artists, many=True, context={'request': request})
    return Response({"artists": serializer.data}, status=200)