from django.urls import path
from .stripe_connect import (
    AccountBalanceView,
    TransactionHistoryView,
    PayoutView,
    OnboardingStatusView
)
from .views import capture_payment_intent, create_payment_intent, get_purchased_tickets_detail, handle_contract_signature, list_tickets
from .webhooks import stripe_webhook

urlpatterns = [
    # Stripe Connect endpoints
    path('stripe/balance/', AccountBalanceView.as_view(), name='stripe-balance'),
    path('stripe/transactions/', TransactionHistoryView.as_view(),
         name='stripe-transactions'),
    path('stripe/payouts/', PayoutView.as_view(), name='stripe-payouts'),
    path('stripe/onboarding-status/', OnboardingStatusView.as_view(),
         name='stripe-onboarding-status'),

    # Payment intents
    path('create-payment-intent/', create_payment_intent, name='create-payment-intent'),
    path('create-payment-intent/<int:gig_id>/', create_payment_intent, name='create-payment-intent-with-gig'),

    # Webhook endpoint
    path('stripe/webhook/', stripe_webhook, name='stripe-webhook'),

    # Tickets
    path('list-tickets/<int:gig_id>/', list_tickets, name='list_tickets'),
    path('list-tickets/', list_tickets, name='list_tickets'),
    path('capturePaymentIntent/',
         capture_payment_intent, name='create-payment-intent'),
    path('ticket-details/<int:gig_id>/', get_purchased_tickets_detail, name='get_purchased_tickets_details'),
    path('handle-payment-intent-succeeded/',handle_contract_signature,name='handle-payment-intent-succeeded'),
]
