
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


class CustomSocialLoginBase(SocialLoginView):
    serializer_class = CustomSocialLoginSerializer

    def save_user(self, request, sociallogin, form=None):
        data = request.data

        role = data.get("role")
        valid_roles = [ROLE_CHOICES.ARTIST,
                       ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]

        if not role or role not in valid_roles:
            raise ValidationError({
                "role": f"Role is required and must be one of {valid_roles}."
            })

        user = super().save_user(request, sociallogin, form)

        if not hasattr(user, 'backend') or user.backend is None:
            from allauth.account.auth_backends import AuthenticationBackend
            user.backend = f"{AuthenticationBackend.__module__}.{AuthenticationBackend.__name__}"

        user.role = role
        user.save()

        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        return user

    def get_response(self):
        original_response = super().get_response()
        user = self.user

        return Response({
            "key": original_response.data.get("key"),
            "role": user.role 
        })


class CustomGoogleLogin(CustomSocialLoginBase):
    adapter_class = GoogleOAuth2Adapter


class CustomAppleLogin(CustomSocialLoginBase):
    adapter_class = AppleOAuth2Adapter
