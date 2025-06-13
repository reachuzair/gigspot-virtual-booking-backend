"""Views for handling payment processing."""
import logging
import json
from decimal import Decimal
from datetime import datetime
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser

# Configure Stripe
import stripe
stripe.api_key = settings.STRIPE_SECRET_KEY
logger = logging.getLogger(__name__)

# Mobile app client names for tracking
MOBILE_APP_CLIENTS = {
    'ios': 'gigspot-ios',
    'android': 'gigspot-android'
}

class PaymentService:
    """
    Service class for handling mobile card payment operations.
    Focused specifically on mobile card payments.
    """
    
    @staticmethod
    def create_payment_intent(user, data, request_meta=None):
        # Import models locally to prevent AppRegistryNotReady error
        from .models import Payment, PaymentStatus, PaymentType, PaymentMethod
        """
        Create payment intent for mobile card payments.
        
        Args:
            user: The user making the payment
            data: Payment data including type and details
            request_meta: Request metadata (unused, kept for compatibility)
            
        Returns:
            tuple: (response_data, status_code)
        """
        try:
            # Validate payment method is provided
            if not data.get('payment_method_id'):
                return {
                    'error': 'Payment method ID is required',
                    'code': 'payment_method_required'
                }, status.HTTP_400_BAD_REQUEST
            
            payment_type = data.get('payment_type')
            
            if payment_type == 'ticket_purchase':
                # Only fans can purchase tickets
                if not hasattr(user, 'fan_profile'):
                    return {
                        'error': 'Only fans can purchase tickets',
                        'code': 'invalid_user_type'
                    }, status.HTTP_403_FORBIDDEN
                return PaymentService._create_ticket_payment_intent(user, data)
            elif payment_type == 'subscription':
                # Only artists and venues can subscribe
                if not hasattr(user, 'artist_profile') and not hasattr(user, 'venue_profile'):
                    return {
                        'error': 'Only artists and venues can subscribe to plans',
                        'code': 'invalid_user_type'
                    }, status.HTTP_403_FORBIDDEN
                return PaymentService._create_subscription_payment_intent(user, data)
            else:
                return {
                    'error': 'Invalid payment type. Must be ticket_purchase or subscription',
                    'code': 'invalid_payment_type'
                }, status.HTTP_400_BAD_REQUEST
            
        except stripe.error.StripeError as e:
            logger.error(f'Stripe error creating payment intent: {str(e)}')
            return {'error': str(e.user_message or str(e))}, status.HTTP_400_BAD_REQUEST
        except Exception as e:
            logger.error(f'Error creating payment intent: {str(e)}', exc_info=True)
            return {'error': 'An error occurred while processing your payment'}, status.HTTP_500_INTERNAL_SERVER_ERROR
    
    @staticmethod
    def _create_ticket_payment_intent(user, data):
        """
        Create payment intent for mobile ticket purchases with card payment.
        
        Args:
            user: The user making the purchase
            data: {
                item_id: ID of the gig (required)
                quantity: Number of tickets (default: 1)
                payment_method_id: Stripe payment method ID (required)
                save_payment_method: Boolean to save card for future use
            }
            
        Returns:
            tuple: (response_data, status_code)
        """
        from gigs.models import Gig  # Local import to avoid circular imports
        
        try:
            gig_id = data.get('item_id')
            if not gig_id:
                return {'error': 'Gig ID is required'}, status.HTTP_400_BAD_REQUEST
                
            quantity = int(data.get('quantity', 1))
            if quantity <= 0:
                return {'error': 'Quantity must be at least 1'}, status.HTTP_400_BAD_REQUEST
                
            payment_method_id = data.get('payment_method_id')
            if not payment_method_id:
                return {'error': 'Payment method ID is required'}, status.HTTP_400_BAD_REQUEST
            
            # Input validation
            if not gig_id:
                return {
                    'error': 'Gig ID is required',
                    'code': 'missing_gig_id'
                }, status.HTTP_400_BAD_REQUEST
                
            if quantity < 1:
                return {
                    'error': 'Quantity must be at least 1',
                    'code': 'invalid_quantity'
                }, status.HTTP_400_BAD_REQUEST
                
            if not payment_method_id:
                return {
                    'error': 'Payment method ID is required',
                    'code': 'payment_method_required'
                }, status.HTTP_400_BAD_REQUEST
            
            with transaction.atomic():
                # Validate gig exists and is active
                try:
                    gig = Gig.objects.select_related('artist', 'venue').select_for_update().get(
                        id=gig_id, 
                        is_active=True
                    )
                except Gig.DoesNotExist:
                    return {
                        'error': 'Gig not found or inactive',
                        'code': 'gig_not_found'
                    }, status.HTTP_404_NOT_FOUND
                
                # Check ticket availability with lock
                if gig.tickets_remaining is not None:
                    if gig.tickets_remaining < quantity:
                        return {
                            'error': 'Not enough tickets available',
                            'code': 'insufficient_tickets',
                            'available': gig.tickets_remaining
                        }, status.HTTP_400_BAD_REQUEST
                    # Reserve tickets
                    gig.tickets_remaining -= quantity
                    gig.save(update_fields=['tickets_remaining'])
                
                # Calculate amount (in cents)
                amount = int(gig.ticket_price * 100) * quantity
                
                # Create or get customer
                customer = PaymentService._get_or_create_customer(user, payment_method_id)
                if isinstance(customer, tuple):
                    return customer  # Return error if customer creation failed
                
                try:
                    # Attach payment method to customer
                    stripe.PaymentMethod.attach(
                        payment_method_id,
                        customer=customer.id
                    )
                    
                    # Create payment intent for mobile
                    intent = stripe.PaymentIntent.create(
                        amount=amount,
                        currency='usd',
                        customer=customer.id,
                        payment_method=payment_method_id,
                        confirm=True,
                        off_session=False,
                        metadata={
                            'user_id': str(user.id),
                            'gig_id': str(gig.id),
                            'type': 'ticket_purchase',
                            'quantity': quantity,
                            'platform': 'mobile'
                        },
                        receipt_email=user.email,
                        setup_future_usage='off_session' if data.get('save_payment_method') else None,
                        payment_method_types=['card']
                    )
                    
                    # Set as default payment method if saving for future use
                    if data.get('save_payment_method'):
                        stripe.Customer.modify(
                            customer.id,
                            invoice_settings={
                                'default_payment_method': payment_method_id
                            }
                        )
                    
                    # Create payment record
                    payment = Payment.objects.create(
                        user=user,
                        amount=Decimal(amount) / 100,
                        currency='usd',
                        status=PaymentStatus.PENDING,
                        payment_type=PaymentType.TICKET_PURCHASE,
                        payment_method=PaymentMethod.CARD,
                        reference_id=intent.id,
                        metadata={
                            'gig_id': str(gig.id),
                            'quantity': quantity,
                            'platform': 'mobile',
                            'payment_method': 'card'
                        }
                    )
                    
                    return {
                        'client_secret': intent.client_secret,
                        'payment_intent_id': intent.id,
                        'payment_id': str(payment.id),
                        'amount': amount,
                        'currency': 'usd',
                        'requires_action': intent.status == 'requires_action',
                        'status': intent.status
                    }, status.HTTP_200_OK
                    
                except stripe.error.CardError as e:
                    # Release reserved tickets on card error
                    if gig.tickets_remaining is not None:
                        gig.tickets_remaining += quantity
                        gig.save(update_fields=['tickets_remaining'])
                    
                    logger.error(f'Card error: {str(e)}')
                    return {
                        'error': e.user_message or 'Card payment failed',
                        'code': e.code or 'card_error',
                        'decline_code': e.error.get('decline_code')
                    }, status.HTTP_400_BAD_REQUEST
                
                except stripe.error.StripeError as e:
                    # Release reserved tickets on Stripe error
                    if gig.tickets_remaining is not None:
                        gig.tickets_remaining += quantity
                        gig.save(update_fields=['tickets_remaining'])
                        
                    logger.error(f'Stripe error: {str(e)}')
                    return {
                        'error': str(e.user_message or 'Payment processing failed'),
                        'code': e.code or 'stripe_error'
                    }, status.HTTP_400_BAD_REQUEST
                
        except ValueError as ve:
            logger.error(f'Validation error in ticket purchase: {str(ve)}')
            return {
                'error': str(ve),
                'code': 'validation_error'
            }, status.HTTP_400_BAD_REQUEST
            
        except Exception as e:
            logger.error(f'Error creating ticket payment intent: {str(e)}', exc_info=True)
            return {
                'error': 'Failed to process payment',
                'code': 'payment_processing_error'
            }, status.HTTP_500_INTERNAL_SERVER_ERROR
            
        except ValueError as ve:
            logger.error(f'Validation error in ticket purchase: {str(ve)}')
            return {'error': str(ve)}, status.HTTP_400_BAD_REQUEST
        except Exception as e:
            logger.error(f'Error creating ticket payment intent: {str(e)}', exc_info=True)
            return {'error': 'Failed to process payment'}, status.HTTP_500_INTERNAL_SERVER_ERROR
    

            


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([])  # Allow any authentication
@csrf_exempt
def create_payment_intent(request):
    # Import models locally to prevent AppRegistryNotReady error
    from .models import Payment, PaymentStatus, PaymentType, PaymentMethod
    from gigs.models import Gig, Ticket
    from subscriptions.models import SubscriptionPlan, VenueAdPlan
    """
    Create a payment intent for ticket purchases or subscriptions.
    
    Request format for gig ticket purchase (fans only):
    {
        "payment_type": "ticket_purchase",
        "item_id": 123,
        "quantity": 1,
        "save_payment_method": false,
        "payment_method_id": "pm_xxx"
    }
    
    Request format for subscription (artists/venues):
    {
        "payment_type": "subscription",
        "plan_id": 1,
        "payment_method_id": "pm_xxx",
        "billing_interval": "month"  # or "year"
    }
    """
    try:
        response, status_code = PaymentService.create_payment_intent(request.user, request.data)
        return Response(response, status=status_code)
    except Exception as e:
        logger.error(f'Unexpected error in create_payment_intent: {str(e)}')
        return Response(
            {'error': 'An unexpected error occurred while processing your request'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

def _create_subscription_payment_intent(user, data):
        """
        Create payment intent for subscription purchases.
        
        Args:
            user: The user subscribing
            data: {
                plan_id: ID of the subscription plan (required)
                payment_method_id: Stripe payment method ID (required)
                billing_interval: 'month' or 'year' (default: 'month')
            }
            
        Returns:
            tuple: (response_data, status_code)
        """
        from subscriptions.models import SubscriptionPlan, VenueAdPlan
        from subscriptions.services import SubscriptionService
        from .models import Payment, PaymentStatus, PaymentType, PaymentMethod
        
        try:
            plan_id = data.get('plan_id')
            payment_method_id = data.get('payment_method_id')
            billing_interval = data.get('billing_interval', 'month')
            
            if not plan_id or not payment_method_id:
                return {
                    'error': 'Plan ID and payment method ID are required',
                    'code': 'missing_required_fields'
                }, status.HTTP_400_BAD_REQUEST
            
            # Determine if user is artist or venue
            is_artist = hasattr(user, 'artist_profile')
            is_venue = hasattr(user, 'venue_profile')
            
            if not (is_artist or is_venue):
                return {
                    'error': 'Only artists and venues can subscribe to plans',
                    'code': 'invalid_user_type'
                }, status.HTTP_403_FORBIDDEN
            
            # Get the appropriate plan
            try:
                if is_artist:
                    plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
                else:  # venue
                    plan = VenueAdPlan.objects.get(id=plan_id, is_active=True)
            except (SubscriptionPlan.DoesNotExist, VenueAdPlan.DoesNotExist):
                return {
                    'error': 'Subscription plan not found',
                    'code': 'plan_not_found'
                }, status.HTTP_404_NOT_FOUND
            
            # Check if user already has an active subscription
            subscription_service = SubscriptionService()
            
            # Create or get customer
            customer = PaymentService._get_or_create_customer(user, payment_method_id)
            if isinstance(customer, tuple):
                return customer  # Return error if customer creation failed
            
            # Create subscription
            subscription_data = {
                'customer_id': customer.id,
                'payment_method_id': payment_method_id,
                'billing_interval': billing_interval,
                'metadata': {
                    'user_id': str(user.id),
                    'plan_id': str(plan.id),
                    'user_type': 'artist' if is_artist else 'venue',
                    'platform': 'mobile'
                }
            }
            
            if is_artist:
                subscription = subscription_service.create_artist_subscription(
                    user, 
                    subscription_data
                )
            else:  # venue
                subscription = subscription_service.create_venue_subscription(
                    user,
                    subscription_data
                )
            
            # Get the latest invoice and payment intent
            latest_invoice = stripe.Invoice.retrieve(subscription.latest_invoice)
            payment_intent = latest_invoice.payment_intent
            
            # Create payment record
            payment = Payment.objects.create(
                user=user,
                amount=Decimal(latest_invoice.amount_due) / 100,
                currency=latest_invoice.currency,
                status=PaymentStatus.PENDING,
                payment_type=PaymentType.SUBSCRIPTION,
                payment_method=PaymentMethod.CARD,
                reference_id=payment_intent.id if payment_intent else None,
                metadata={
                    'subscription_id': str(subscription.id),
                    'plan_id': str(plan.id),
                    'billing_cycle': billing_interval,
                    'user_type': 'artist' if is_artist else 'venue'
                }
            )
            
            return {
                'client_secret': payment_intent.client_secret if payment_intent else None,
                'subscription_id': str(subscription.id),
                'payment_intent_id': payment_intent.id if payment_intent else None,
                'payment_id': str(payment.id),
                'status': subscription.status,
                'requires_action': payment_intent and payment_intent.status == 'requires_action',
                'subscription_status': subscription.status,
                'current_period_end': subscription.current_period_end
            }, status.HTTP_200_OK
            
        except stripe.error.CardError as e:
            logger.error(f'Card error during subscription: {str(e)}')
            return {
                'error': e.user_message or 'Card payment failed',
                'code': e.code or 'card_error',
                'decline_code': getattr(e, 'decline_code', None)
            }, status.HTTP_400_BAD_REQUEST
            
        except stripe.error.StripeError as e:
            logger.error(f'Stripe error during subscription: {str(e)}')
            return {
                'error': str(e.user_message or 'Failed to create subscription'),
                'code': getattr(e, 'code', 'stripe_error'),
                'decline_code': getattr(e, 'decline_code', None)
            }, status.HTTP_400_BAD_REQUEST
            
        except Exception as e:
            logger.error(f'Error in subscription payment intent: {str(e)}', exc_info=True)
            return {
                'error': 'An error occurred while processing your subscription',
                'code': 'subscription_error'
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

def _get_or_create_customer(user, payment_method_id=None):
    # Import models locally to prevent AppRegistryNotReady error
    from .models import PaymentMethod, Payment
    """Helper to get or create a Stripe customer for the user."""
    try:
        # Check if user already has a Stripe customer ID
        customer_id = None
        if hasattr(user, 'artist_profile') and user.artist_profile.stripe_customer_id:
            customer_id = user.artist_profile.stripe_customer_id
        elif hasattr(user, 'venue_profile') and user.venue_profile.stripe_customer_id:
            customer_id = user.venue_profile.stripe_customer_id
        
        # If customer exists, retrieve and update payment method if needed
        if customer_id:
            try:
                customer = stripe.Customer.retrieve(customer_id)
                
                # Attach new payment method if provided
                if payment_method_id:
                    payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
                    payment_method.attach(customer=customer.id)
                    
                    # Set as default payment method
                    stripe.Customer.modify(
                        customer.id,
                        invoice_settings={
                            'default_payment_method': payment_method.id
                        }
                    )
                return customer
                
            except stripe.error.InvalidRequestError:
                # Customer not found in Stripe, will create new one
                pass
        
        # Create new customer
        customer_data = {
            'email': user.email,
            'name': user.get_full_name() or user.email.split('@')[0],
            'metadata': {
                'user_id': user.id,
                'user_type': user.role.lower()
            }
        }
        
        if payment_method_id:
            customer_data['payment_method'] = payment_method_id
            customer_data['invoice_settings'] = {
                'default_payment_method': payment_method_id
            }
        
        customer = stripe.Customer.create(**customer_data)
        
        # Save customer ID to the appropriate profile
        if hasattr(user, 'artist_profile'):
            user.artist_profile.stripe_customer_id = customer.id
            user.artist_profile.save()
        elif hasattr(user, 'venue_profile'):
            user.venue_profile.stripe_customer_id = customer.id
            user.venue_profile.save()
        
        return customer
        
    except Exception as e:
        logger.error(f'Error in _get_or_create_customer: {str(e)}')
        raise

def list_tickets(request, gig_id):
    # Import models locally to prevent AppRegistryNotReady error
    from gigs.models import Ticket, Gig
    from .models import Payment
    """
    List all tickets for a specific gig for the authenticated user.
    """
    try:
        # Verify the gig exists and is active
        try:
            gig = Gig.objects.get(id=gig_id, is_active=True)
        except Gig.DoesNotExist:
            return Response(
                {'detail': 'Gig not found or inactive'}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        # Only allow the gig owner to view tickets
        if gig.user != request.user and request.user.role != 'ADMIN':
            return Response(
                {'detail': 'Not authorized to view these tickets'}, 
                status=status.HTTP_403_FORBIDDEN
            )
            
        # Get all tickets for this gig
        tickets = Ticket.objects.filter(gig=gig).select_related('user')
        
        # Serialize the tickets
        ticket_data = [{
            'id': ticket.id,
            'user': {
                'id': ticket.user.id,
                'name': ticket.user.get_full_name() or ticket.user.email,
                'email': ticket.user.email
            },
            'status': ticket.status,
            'purchase_date': ticket.created_at,
            'ticket_type': ticket.ticket_type,
            'quantity': ticket.quantity,
            'total_paid': str(ticket.total_paid)
        } for ticket in tickets]
        
        return Response({
            'gig': {
                'id': gig.id,
                'title': gig.title,
                'date': gig.date_time,
                'total_tickets_sold': len(ticket_data),
                'total_revenue': str(sum(float(t['total_paid']) for t in ticket_data))
            },
            'tickets': ticket_data
        })
        
    except Exception as e:
        logger.error(f'Error in list_tickets: {str(e)}')
        return Response(
            {'detail': 'An error occurred while retrieving tickets'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
