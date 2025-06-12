
import json
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter

from custom_auth.models import ROLE_CHOICES, Artist, Fan, Venue

from allauth.account.auth_backends import AuthenticationBackend as AllauthBackend

from allauth.account.adapter import get_adapter
from rest_framework.response import Response
from social_auth.serializers import CustomSocialLoginSerializer


# class CustomSocialLoginBase(SocialLoginView):
#     serializer_class = CustomSocialLoginSerializer

#     def save_user(self, request, sociallogin, form=None):
#         data = request.data

#         role = data.get("role")
#         valid_roles = [ROLE_CHOICES.ARTIST,
#                        ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]

#         if not role or role not in valid_roles:
#             raise ValidationError({
#                 "role": f"Role is required and must be one of {valid_roles}."
#             })

#         user = super().save_user(request, sociallogin, form)

#         if not hasattr(user, 'backend') or user.backend is None:
#             from allauth.account.auth_backends import AuthenticationBackend
#             user.backend = f"{AuthenticationBackend.__module__}.{AuthenticationBackend.__name__}"

#         user.role = role
#         user.save()

#         if role == ROLE_CHOICES.ARTIST:
#             Artist.objects.get_or_create(user=user)
#         elif role == ROLE_CHOICES.VENUE:
#             Venue.objects.get_or_create(user=user)
#         elif role == ROLE_CHOICES.FAN:
#             Fan.objects.get_or_create(user=user)

#         return user

#     def get_response(self):
#         original_response = super().get_response()
#         user = self.user

#         return Response({
#             "key": original_response.data.get("key"),
#             "role": user.role 
#         })


# class CustomGoogleLogin(CustomSocialLoginBase):
#     adapter_class = GoogleOAuth2Adapter


# class CustomAppleLogin(CustomSocialLoginBase):
#     adapter_class = AppleOAuth2Adapter

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import login
from django.utils import timezone
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
        user.backend = 'socialauth.google_auth.GoogleAuthBackend'
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
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        }, status=status.HTTP_200_OK)

    return Response({'detail': _('Google authentication failed.')}, status=status.HTTP_401_UNAUTHORIZED)
