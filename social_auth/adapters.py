from allauth.account.utils import send_email_confirmation
from django.http import QueryDict
from custom_auth.models import User, ROLE_CHOICES, Artist, Venue, Fan
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email, user_username
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from custom_auth.models import ROLE_CHOICES, Artist, User, Venue, Fan

import logging

logger = logging.getLogger(__name__)


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        email = user.email
        if email:
            email_addresses = EmailAddress.objects.filter(
                user=user, email=email)
            if email_addresses.exists():
                email_address = email_addresses.first()
                created = False
            else:
                email_address = EmailAddress.objects.create(
                    user=user, email=email)
                created = True

            if not email_address.verified:
                send_email_confirmation(request, user)

        return user
