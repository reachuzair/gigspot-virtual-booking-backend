"""Stripe client configuration for subscriptions."""
import stripe
from django.conf import settings

# Initialize Stripe with the API key from Django settings
stripe.api_key = settings.STRIPE_SECRET_KEY

# Set the API version to ensure compatibility
stripe.api_version = '2023-10-16'

# Configure the Stripe client with app info
stripe.set_app_info(
    'GigSpot',
    version='1.0.0',
    url='https://gigspot.app'
)
