import requests
import jwt
from jwt.algorithms import RSAAlgorithm
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.contrib.auth import get_user_model
from gigspot_backend import settings

User = get_user_model()

class AppleAuthBackend:
    def authenticate(self, request, apple_token=None, **kwargs):
        if not apple_token:
            return None
        try:
            apple_keys = requests.get('https://appleid.apple.com/auth/keys').json()
            header = jwt.get_unverified_header(apple_token)
            key = next(k for k in apple_keys['keys'] if k['kid'] == header['kid'])
            public_key = RSAAlgorithm.from_jwk(key)
            decoded = jwt.decode(
                apple_token,
                key=public_key,
                audience=settings.APPLE_CLIENT_ID,  
                algorithms=['RS256']
            )
            email = decoded.get('email')
            full_name = request.data.get('name', '')  
            if not email:
                return None
        except Exception as e:
            return None
        try:
            user = User.objects.get(email=email)
        except ObjectDoesNotExist:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    name=full_name or email.split('@')[0],
                    is_active=True
                )
        user.name = full_name or user.name
        user.is_active = True
        user.save()
        return user
