from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import User, Artist, Venue, Fan
from custom_auth.models import ROLE_CHOICES

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    try:
        user = request.user
        if user.role == ROLE_CHOICES.ARTIST:
            artist = Artist.objects.filter(user=user).first()
            return Response({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'artist': artist
            })
        elif user.role == ROLE_CHOICES.VENUE:
            venue = Venue.objects.filter(user=user).first()
            return Response({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'venue': venue
            })
        elif user.role == ROLE_CHOICES.FAN:
            fan = Fan.objects.filter(user=user).first()
            return Response({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'fan': fan
            })
        else:
            return Response({
                'id': user.id,
                'email': user.email,
                'role': user.role
            })
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
