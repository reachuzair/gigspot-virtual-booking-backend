"""
Webhook handlers for Stripe payment events.

This module handles Stripe webhook events related to payments.
"""
import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.utils import timezone

from .stripe_client import stripe
from .models import Payment, PaymentStatus
from .helpers import handle_account_update

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(['POST'])
@permission_classes([AllowAny])
def stripe_webhook(request):
    """
    Handle Stripe webhook events for payments.
    
    This view processes payment-related Stripe webhook events.
    """
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    
    if not webhook_secret:
        logger.error('STRIPE_WEBHOOK_SECRET is not set in settings')
        return JsonResponse(
            {'detail': 'Webhook configuration error'}, 
            status=500
        )
    
    try:
        event = stripe.Webhook.construct_event(
            payload, 
            sig_header, 
            webhook_secret
        )
    except ValueError as e:
        logger.error(f'Webhook error while parsing request: {str(e)}')
        return JsonResponse(
            {'detail': 'Invalid payload'}, 
            status=400
        )
    except stripe.error.SignatureVerificationError as e:
        logger.error(f'Webhook signature verification failed: {str(e)}')
        return JsonResponse(
            {'detail': 'Invalid signature'}, 
            status=400
        )
    except Exception as e:
        logger.error(f'Unexpected error in webhook: {str(e)}', exc_info=True)
        return JsonResponse(
            {'detail': 'Webhook processing failed'},
            status=400
        )
    
    # Handle the event
    event_type = event['type']
    logger.info(f'Received webhook event: {event_type}')
    
    try:
        if event_type == 'payment_intent.succeeded':
            logger.info('Payment intent succeeded')
            handle_payment_success(event['data']['object'])
        elif event_type == 'payment_intent.payment_failed':
            handle_payment_failure(event['data']['object'])
        elif event_type in ['charge.succeeded', 'charge.failed']:
            handle_charge_event(event['data']['object'])
        elif event_type == 'account.updated':
            handle_account_update(event['data']['object'])
        else:
            logger.info(f'Unhandled event type: {event_type}')
            
        return JsonResponse({'status': 'success'})
        
    except Exception as e:
        logger.error(f'Error handling webhook event {event_type}: {str(e)}', exc_info=True)
        return JsonResponse(
            {'detail': 'Error processing webhook'}, 
            status=400
        )

def handle_payment_success(payment_intent):
    """
    Handle successful payment intent.
    
    Args:
        payment_intent: The Stripe payment intent object
    """
    try:
        payment_intent_id = payment_intent.get('id')
        amount = payment_intent.get('amount')
        currency = payment_intent.get('currency')
        metadata = payment_intent.get('metadata', {})
        
        logger.info(f'Handling successful payment for intent: {payment_intent_id}')
        logger.info(f'Payment metadata: {metadata}')
        if metadata.get('payment_intent_for') == 'contract_signature':
            logger.info('Processing contract signature payment')
            from .helpers import handle_payment_intent_succeeded
            handle_payment_intent_succeeded(payment_intent)
            # Handle contract signature payment logic here
            # For example, update contract status, notify parties, etc.
            
        # Check if this is a ticket purchase
        if metadata.get('payment_intent_for') == 'ticket_purchase':
            logger.info('Processing ticket purchase payment')
            from .helpers import handle_payment_intent_succeeded
            handle_payment_intent_succeeded(payment_intent)
            logger.info('Successfully processed ticket purchase')
        
        # Update payment status in database
        try:
            payment = Payment.objects.get(payment_intent_id=payment_intent_id)
            payment.status = PaymentStatus.COMPLETED
            payment.save(update_fields=['status', 'updated_at'])
            
            logger.info(f'Payment {payment_intent_id} marked as completed')
            
        except Payment.DoesNotExist:
            logger.warning(f'Payment not found for intent: {payment_intent_id}')
            
    except Exception as e:
        logger.error(f'Error handling payment success: {str(e)}', exc_info=True)
        raise

def handle_payment_failure(payment_intent):
    """
    Handle failed payment intent.
    
    Args:
        payment_intent: The failed Stripe payment intent object
    """
    try:
        payment_intent_id = payment_intent.get('id')
        last_payment_error = payment_intent.get('last_payment_error', {})
        
        # Update payment status in database
        try:
            payment = Payment.objects.get(reference_id=payment_intent_id)
            payment.status = PaymentStatus.FAILED
            payment.metadata = payment.metadata or {}
            payment.metadata['failure_reason'] = last_payment_error.get('message', 'Unknown error')
            payment.metadata['failure_code'] = last_payment_error.get('code')
            payment.save(update_fields=['status', 'metadata', 'updated_at'])
            
            logger.warning(f'Payment {payment_intent_id} failed: {last_payment_error.get("message")}')
            
        except Payment.DoesNotExist:
            logger.warning(f'Payment not found for failed intent: {payment_intent_id}')
            
    except Exception as e:
        logger.error(f'Error handling payment failure: {str(e)}', exc_info=True)
        raise

def handle_charge_event(charge):
    """
    Handle charge events from Stripe.
    
    Args:
        charge: The Stripe charge object
    """
    try:
        charge_id = charge.get('id')
        payment_intent_id = charge.get('payment_intent')
        
        if not payment_intent_id:
            logger.info(f'No payment intent ID found for charge {charge_id}')
            return
            
        # Update payment with charge details if needed
        try:
            payment = Payment.objects.get(reference_id=payment_intent_id)
            if not payment.charge_id:
                payment.charge_id = charge_id
                payment.save(update_fields=['charge_id', 'updated_at'])
                logger.info(f'Updated payment {payment_intent_id} with charge ID {charge_id}')
                
        except Payment.DoesNotExist:
            logger.warning(f'Payment not found for charge: {payment_intent_id}')
            
    except Exception as e:
        logger.error(f'Error handling charge event: {str(e)}', exc_info=True)
        raise
