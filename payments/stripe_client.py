"""Stripe client configuration and utilities."""
import os
import stripe
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Initialize Stripe with the API key from settings
stripe.api_key = getattr(settings, 'STRIPE_SECRET_KEY', None)

if not stripe.api_key:
    raise ImproperlyConfigured(
        'STRIPE_SECRET_KEY is not set in Django settings.'
        ' Please add it to your settings file.'
    )

# Set the API version to ensure compatibility
stripe.api_version = '2023-10-16'

# Configure Stripe with additional settings if needed
stripe.set_app_info(
    'GigSpot',
    version='1.0.0',
    url='https://gigspot.app'
)

# Export the configured Stripe client
export = stripe
