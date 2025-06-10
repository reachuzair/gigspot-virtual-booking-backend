
import json
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter

from custom_auth.models import ROLE_CHOICES, Artist, Fan, Venue

from allauth.account.auth_backends import AuthenticationBackend as AllauthBackend


class CustomSocialLoginBase(SocialLoginView):
    def save_user(self, request, sociallogin, form=None):

        try:
            if request.content_type == 'application/json':
                data = json.loads(request.body)
            else:
                data = request.POST
        except Exception:
            raise ValidationError({"role": "Invalid request data."})

        role = data.get("role")
        valid_roles = [ROLE_CHOICES.ARTIST,
                       ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]

        if role not in valid_roles:
            raise ValidationError({
                "role": f"Role is required and must be one of {valid_roles}."
            })

        user = super().save_user(request, sociallogin, form)
        if not hasattr(user, 'backend') or user.backend is None:
            user.backend = AllauthBackend.__module__ + '.' + AllauthBackend.__name__

        user.role = role
        user.save()

        # Create profile
        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        return user


class CustomGoogleLogin(CustomSocialLoginBase):
    adapter_class = GoogleOAuth2Adapter


class CustomAppleLogin(CustomSocialLoginBase):
    adapter_class = AppleOAuth2Adapter
