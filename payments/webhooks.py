import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import stripe
from .models import Payment, Payout, BankAccount, PayoutStatus
from custom_auth.models import Artist, Fan
from gigs.models import Gig
from .helpers import handle_account_update

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):

    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')
    
    if not webhook_secret:
        logger.error('STRIPE_WEBHOOK_SECRET is not set in settings')
        return JsonResponse({'error': 'Webhook configuration error'}, status=500)
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError as e:
        logger.error(f'⚠️  Webhook error while parsing request: {str(e)}')
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f'⚠️  Webhook signature verification failed: {str(e)}')
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    except Exception as e:
        logger.error(f'Unexpected error in webhook: {str(e)}')
        return JsonResponse({'error': 'Webhook handler failed'}, status=500)

    logger.info(f'Received Stripe event: {event.type}')

    if event.type == 'payment_intent.succeeded':
        logger.info('Processing payment_intent.succeeded event')
        handle_payment_success(event.data.object)
    
    elif event.type == 'account.updated':
        logger.info('Processing account.updated event')
        handle_account_update(event.data.object)
    
    elif event.type == 'account.external_account.updated':
        
        external_account = event.data.object
        bank_account_id = external_account.get('id')
        
        try:
            bank_account = BankAccount.objects.get(stripe_bank_account_id=bank_account_id)
            bank_account.is_verified = external_account.get('status') == 'verified'
            bank_account.last_verification_attempt = timezone.now()
            
            if external_account.get('status') == 'verification_failed':
                bank_account.verification_fail_reason = external_account.get('verification', {}).get('details')
            
            bank_account.save()
            logger.info(f'Updated bank account {bank_account_id} verification status to {bank_account.is_verified}')
            
        except BankAccount.DoesNotExist:
            logger.warning(f'Bank account not found: {bank_account_id}')
    
    elif event.type == 'payout.paid':
        # Handle successful payout
        payout_data = event.data.object
        try:
            payout = Payout.objects.get(stripe_payout_id=payout_data['id'])
            payout.status = PayoutStatus.PAID
            payout.completed_at = timezone.now()
            payout.save()
            logger.info(f'Payout {payout.id} marked as paid')
        except Payout.DoesNotExist:
            logger.warning(f'Payout not found: {payout_data["id"]}')
    
    elif event.type == 'payout.failed':
        # Handle failed payout
        payout_data = event.data.object
        try:
            payout = Payout.objects.get(stripe_payout_id=payout_data['id'])
            payout.status = PayoutStatus.FAILED
            payout.failure_message = payout_data.get('failure_message', 'Unknown error')
            payout.save()
            logger.warning(f'Payout {payout.id} failed: {payout.failure_message}')
        except Payout.DoesNotExist:
            logger.warning(f'Payout not found: {payout_data["id"]}')
    
    elif event.type == 'payout.canceled':
        # Handle canceled payout
        payout_data = event.data.object
        try:
            payout = Payout.objects.get(stripe_payout_id=payout_data['id'])
            payout.status = PayoutStatus.CANCELED
            payout.save()
            logger.info(f'Payout {payout.id} was canceled')
        except Payout.DoesNotExist:
            logger.warning(f'Payout not found: {payout_data["id"]}')
    
    # Return a 200 response to acknowledge receipt of the webhook
    return JsonResponse({'status': 'success'})

def handle_payment_success(payment_intent):

    try:
        logger.info(f'Processing successful payment: {payment_intent["id"]}')
        
        # Get metadata from payment intent
        metadata = payment_intent.get('metadata', {})
        gig_id = metadata.get('gig_id')
        fan_id = metadata.get('fan_id')
        quantity = int(metadata.get('quantity', 1))
        
        if not gig_id or not fan_id:
            logger.error('Missing gig_id or fan_id in payment intent metadata')
            return
        
        # Get related objects
        gig = Gig.objects.get(id=gig_id)
        fan = Fan.objects.get(id=fan_id)
        
        # Create payment record
        payment = Payment.objects.create(
            gig=gig,
            fan=fan,
            amount=payment_intent['amount'] / 100,  # Convert from cents
            stripe_payment_intent_id=payment_intent['id'],
            status='succeeded',
            metadata=metadata
        )
        
        logger.info(f'Created payment record: {payment.id}')
        
        # TODO: Add any additional processing here (e.g., create tickets, send notifications)
        
    except Exception as e:
        logger.error(f'Error processing payment success: {str(e)}')
        raise  # Re-raise to ensure it's logged by the webhook handler