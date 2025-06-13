from custom_auth.models import ROLE_CHOICES, Artist, Venue, Fan
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import login
from django.utils import timezone
from social_auth.apple_auth import AppleAuthBackend
from social_auth.google_auth import GoogleAuthBackend  

@api_view(['POST'])
@permission_classes([AllowAny])
def google_login(request):
    google_token = request.data.get('token')
    role = request.data.get('role')

    valid_roles = [ROLE_CHOICES.ARTIST, ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]

    if not google_token:
        return Response({'detail': _('Google token is required.')}, status=status.HTTP_400_BAD_REQUEST)

    if not role or role not in valid_roles:
        return Response({'detail': _(f"Role is required and must be one of {valid_roles}.")}, status=status.HTTP_400_BAD_REQUEST)

    user = GoogleAuthBackend().authenticate(request, google_token=google_token)

    if user is not None:
        user.backend = 'social_auth.google_auth.GoogleAuthBackend'
        user.role = role
        user.save()
        login(request, user)

        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        profile_image_url = (
            request.build_absolute_uri(user.profileImage.url)
            if user.profileImage else
            getattr(user, '_google_picture_url', None)
        )

        return Response({
            'success': True,
            'role': user.role,
            'user': {
                'email': user.email,
                'name': user.name,
                'profileImage': profile_image_url
            }
        }, status=status.HTTP_200_OK)

    return Response({'detail': _('Google authentication failed.')}, status=status.HTTP_401_UNAUTHORIZED)

@api_view(['POST'])
@permission_classes([AllowAny])
def apple_login(request):
    apple_token = request.data.get('token')
    role = request.data.get('role')

    valid_roles = [ROLE_CHOICES.ARTIST, ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]

    if not apple_token:
        return Response({'detail': _('Apple token is required.')}, status=status.HTTP_400_BAD_REQUEST)

    if not role or role not in valid_roles:
        return Response({'detail': _(f"Role is required and must be one of {valid_roles}.")}, status=status.HTTP_400_BAD_REQUEST)

    user = AppleAuthBackend().authenticate(request, apple_token=apple_token)

    if user is not None:
        user.backend = 'social_auth.apple_auth.AppleAuthBackend'
        user.role = role
        user.save()
        login(request, user)

        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        return Response({
            'success': True,
            'role': user.role,
            'user': {
                'email': user.email,
                'name': user.name,
                'profileImage': request.build_absolute_uri(user.profileImage.url) if user.profileImage else None
            }
        }, status=status.HTTP_200_OK)

    return Response({'detail': _('Apple authentication failed.')}, status=status.HTTP_401_UNAUTHORIZED)