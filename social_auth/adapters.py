from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from custom_auth.models import ROLE_CHOICES, Artist, User, Venue, Fan

import logging

logger = logging.getLogger(__name__)


logger = logging.getLogger(__name__)


from allauth.account.utils import user_email, user_username
from allauth.account.models import EmailAddress
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from custom_auth.models import User, ROLE_CHOICES, Artist, Venue, Fan
from django.http import QueryDict
from allauth.account.utils import send_email_confirmation


class CustomSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        # Extract role from request
        role = ROLE_CHOICES.FAN
        if hasattr(request, "POST"):
            data = request.POST if isinstance(request.POST, QueryDict) else request.body
            role = request.POST.get("role") or ROLE_CHOICES.FAN

        user.role = role
        user.save()

        # Create related model
        if role == ROLE_CHOICES.ARTIST:
            Artist.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.VENUE:
            Venue.objects.get_or_create(user=user)
        elif role == ROLE_CHOICES.FAN:
            Fan.objects.get_or_create(user=user)

        # Send verification email if not already verified
        email = user.email
        if email:
            email_address, created = EmailAddress.objects.get_or_create(user=user, email=email)
            if not email_address.verified:
                send_email_confirmation(request, user)

        return user

