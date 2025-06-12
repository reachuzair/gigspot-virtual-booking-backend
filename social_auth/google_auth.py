import requests
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction

User = get_user_model()

class GoogleAuthBackend:
    def authenticate(self, request, google_token=None, **kwargs):
        if not google_token:
            return None

        # Step 1: Verify the token with Google
        try:
            response = requests.get(
                'https://oauth2.googleapis.com/tokeninfo',
                params={'id_token': google_token},
                timeout=5  # optional timeout for safety
            )
            if response.status_code != 200:
                return None

            data = response.json()
            email = data.get('email')
            if not email:
                return None
        except Exception:
            return None

        # Step 2: Get or create user
        try:
            user = User.objects.get(email=email)
        except ObjectDoesNotExist:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    username=email,
                    first_name=data.get('given_name', ''),
                    last_name=data.get('family_name', ''),
                    is_active=True,
                )

        # Step 3: Update basic info on every login
        user.first_name = data.get('given_name', '')
        user.last_name = data.get('family_name', '')
        user.is_active = True
        user.save()

        return user

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
