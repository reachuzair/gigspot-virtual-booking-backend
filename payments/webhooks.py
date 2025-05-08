from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import stripe
from .models import Payment
from custom_auth.models import Artist, Fan
from gigs.models import Gig
from .helpers import handle_account_update
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']
    event = None

    try:
        logger.info('Stripe webhook received')
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        logger.error('Stripe webhook error: %s', str(e))
        return Response({"error": str(e)}, status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error('Stripe webhook error: %s', str(e))
        return Response({"error": str(e)}, status=400)

    # Handle specific events
    if event['type'] == 'payment_intent.succeeded':
        logger.info('Payment intent succeeded')
        handle_payment_success(event['data']['object'])
    elif event['type'] == 'account.updated':
        logger.info('Account updated')
        handle_account_update(event['data']['object'])
    elif event['type'] == 'payout.paid':
        logger.info('Payout paid')
        handle_payout_paid(event['data']['object'])

    return Response({"status": "success"})

    

# def handle_payment_success(payment_intent):
#     # Create ticket and record transaction
#     gig_id = payment_intent['metadata']['gig_id']
#     fan_id = payment_intent['metadata']['fan_id']
#     quantity = int(payment_intent['metadata']['quantity'])
    
#     gig = Gig.objects.get(id=gig_id)
#     fan = Fan.objects.get(id=fan_id)
    
#     # Create tickets
#     for _ in range(quantity):
#         Ticket.objects.create(
#             show=show,
#             fan=fan,
#             payment_intent_id=payment_intent['id'],
#             amount=payment_intent['amount'] / 100
#         )
    
#     # Record transaction
#     Transaction.objects.create(
#         artist=show.artist,
#         amount=payment_intent['amount'] - payment_intent['application_fee_amount'],
#         fee=payment_intent['application_fee_amount'],
#         payment_intent_id=payment_intent['id'],
#         status='completed'
#     )