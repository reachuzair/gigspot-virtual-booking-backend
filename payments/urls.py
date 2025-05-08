from django.urls import path
from . import views
from .webhooks import stripe_webhook

urlpatterns = [
    path('webhook/', stripe_webhook, name='stripe_webhook'),
]