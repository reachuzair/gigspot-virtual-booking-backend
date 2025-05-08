from django.urls import path
from .webhooks import stripe_webhook
from .views import fetch_balance

urlpatterns = [
    path('webhook/', stripe_webhook, name='stripe_webhook'),
    path('balance/', fetch_balance, name='fetch_balance'),
]