import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

User = get_user_model()


class GoogleAuthBackend:
    def authenticate(self, request, google_token=None, **kwargs):
        if not google_token:
            return None

        try:
            token_info = requests.get(
                'https://www.googleapis.com/oauth2/v1/tokeninfo',
                params={'access_token': google_token},
                timeout=5
            )
            if token_info.status_code != 200:
                return None

            email = token_info.json().get('email')
            if not email:
                return None
            profile_resp = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {google_token}'},
                timeout=5
            )
            if profile_resp.status_code != 200:
                return None

            profile = profile_resp.json()
            full_name = profile.get('name', '').strip()
            picture = profile.get('picture')

        except Exception:
            return None
        try:
            user = User.objects.get(email=email)
        except ObjectDoesNotExist:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    name=full_name,
                    is_active=True
                )
        user.name = full_name or user.name
        user.is_active = True
        user.save()
        user._google_picture_url = picture
        return user
