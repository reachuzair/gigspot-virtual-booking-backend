# urls.py
from django.urls import path
from .views import (
    subscription_plans,
    create_artist_subscription,
    manage_artist_subscription,
    payment_methods,
    test_create_artist_subscription
)
# from .webhooks import stripe_webhook

urlpatterns = [
    path('plans/', subscription_plans, name='subscription-plans'),
    path('create/', create_artist_subscription, name='create-subscription'),
    path('test-create/', test_create_artist_subscription, name='test-create-subscription'),
    path('manage/', manage_artist_subscription, name='manage-subscription'),
    path('payment-methods/', payment_methods, name='payment-methods'),
    # path('stripe/webhook/', stripe_webhook, name='stripe-webhook'),
]