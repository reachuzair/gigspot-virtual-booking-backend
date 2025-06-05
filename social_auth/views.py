import json
from rest_framework.exceptions import ValidationError
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter

from custom_auth.models import ROLE_CHOICES, Artist, Fan, Venue


class CustomSocialLoginBase(SocialLoginView):

    def save_user(self, request, sociallogin, form=None):
        print("Content-Type:", request.content_type)
        print("Raw body:", request.body)
        # Decode and parse JSON body
        try:
            body_unicode = request.body.decode('utf-8')
            if not body_unicode:
                raise ValidationError({"role": "Request body is empty."})
            data = json.loads(body_unicode)
        except Exception:
            raise ValidationError({"role": "Invalid JSON body."})

        role = data.get("role")
        valid_roles = [ROLE_CHOICES.ARTIST,
                       ROLE_CHOICES.VENUE, ROLE_CHOICES.FAN]
        if role not in valid_roles:
            raise ValidationError({
                "role": f"Role is required and must be one of {valid_roles}."
            })

        # Save the user (creates if new)
        user = super().save_user(request, sociallogin, form)

        # Update role
        user.role = role
        user.save()

        # Avoid duplicate profile creation if it already exists
        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        return user


class CustomGoogleLogin(CustomSocialLoginBase):
    adapter_class = GoogleOAuth2Adapter

    def dispatch(self, *args, **kwargs):
        print("CustomGoogleLogin dispatch called")
        return super().dispatch(*args, **kwargs)

    def save_user(self, request, sociallogin, form=None):
        print("save_user called")
        print("Content-Type:", request.content_type)
        print("Raw body:", request.body)


class CustomAppleLogin(CustomSocialLoginBase):
    adapter_class = AppleOAuth2Adapter
