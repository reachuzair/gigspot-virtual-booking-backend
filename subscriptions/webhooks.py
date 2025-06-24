import datetime
from django.conf import settings
from rest_framework.decorators import api_view
from rest_framework.response import Response
import stripe
from .models import ArtistSubscription

stripe.api_key = settings.STRIPE_SECRET_KEY

@api_view(['POST'])
def payment_intent(request):
    # Verify webhook signature
    signature = request.META.get('HTTP_STRIPE_SIGNATURE')
    if not signature:
        return Response(status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload=request.body,
            sig_header=signature,
            secret=settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return Response(status=400)
    except stripe.error.SignatureVerificationError:
        return Response(status=400)

    # Handle different event types
    if event['type'] == 'payment_intent.succeeded':
        payment_intent = event['data']['object']
        customer_id = payment_intent['customer']
        
        # Find the artist subscription
        subscription = ArtistSubscription.objects.filter(
            stripe_customer_id=customer_id
        ).first()
        
        if subscription:
            # Update subscription status
            subscription.status = 'active'
            subscription.save()
            
            # Send notification to artist
            # (You can implement your notification system here)
            
    elif event['type'] == 'invoice.payment_succeeded':
        invoice = event['data']['object']
        customer_id = invoice['customer']
        
        subscription = ArtistSubscription.objects.filter(
            stripe_customer_id=customer_id
        ).first()
        
        if subscription:
            # Update subscription period
            subscription.current_period_end = datetime.fromtimestamp(
                invoice['lines']['data'][0]['period']['end']
            )
            subscription.save()
            
    elif event['type'] == 'invoice.payment_failed':
        invoice = event['data']['object']
        customer_id = invoice['customer']
        
        subscription = ArtistSubscription.objects.filter(
            stripe_customer_id=customer_id
        ).first()
        
        if subscription:
            subscription.status = 'past_due'
            subscription.save()
            
    return Response(status=200)