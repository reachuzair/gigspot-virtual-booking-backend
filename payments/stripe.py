"""
Stripe integration module for the payments app.

This module provides access to the Stripe client and related utilities.
"""
import logging
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

# This will be set to the Stripe client when the app is ready
_stripe = None
_initialized = False

def get_stripe_client():
    """
    Get the Stripe client instance.
    
    Returns:
        The configured Stripe client instance.
        
    Raises:
        RuntimeError: If the Stripe client has not been initialized yet.
    """
    if not _initialized:
        raise RuntimeError(
            'Stripe client not initialized. This usually means the Django app '
            'is still starting up. Make sure to access the Stripe client '
            'after the app has fully loaded.'
        )
    return _stripe

# Create a proxy to the stripe module that will be initialized later
class StripeProxy:
    def __getattr__(self, name):
        if not _initialized:
            raise RuntimeError(
                'Stripe client not initialized. This usually means the Django app '
                'is still starting up. Make sure to access the Stripe client '
                'after the app has fully loaded.'
            )
        return getattr(_stripe, name)

# This will be imported by other modules
stripe = StripeProxy()
