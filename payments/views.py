
from decimal import ROUND_HALF_UP, Decimal
import logging
import json
from decimal import Decimal
import datetime
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from custom_auth.models import Artist
from gigs.models import Contract, Gig
from payments.models import Payment, PaymentStatus
from rest_framework.views import APIView
from rest_framework.parsers import JSONParser
# Configure Stripe
import stripe
logger = logging.getLogger(__name__)
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
    def _get_or_create_customer(user, payment_method_id=None):
        """
        Get or create a Stripe customer for the user.
        
        Args:
            user: The user to get or create a customer for
            payment_method_id: Optional Stripe payment method ID to attach
            
        Returns:
            stripe.Customer: The Stripe customer object
            or tuple: (error_response, status_code) if an error occurs
        """
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
            customer_name = None
            if hasattr(user, 'get_full_name') and callable(getattr(user, 'get_full_name')):
                customer_name = user.get_full_name()
            
            if not customer_name or not customer_name.strip():
                # Try to get name from billing details if available
                billing_details = getattr(user, 'billing_details', {}) or {}
                customer_name = billing_details.get('name') or user.email.split('@')[0]
            
            customer_data = {
                'email': user.email,
                'name': customer_name,
                'metadata': {
                    'user_id': user.id,
                    'user_type': getattr(user, 'role', 'user').lower()
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
            return {
                'error': 'Failed to create or retrieve customer',
                'details': str(e)
            }, status.HTTP_500_INTERNAL_SERVER_ERROR

    @staticmethod
    def create_payment_intent(user, data, request_meta=None):
        # Import models locally to prevent AppRegistryNotReady error
        from .models import PaymentStatus
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
                    'detail': 'Payment method ID is required',
                    'code': 'payment_method_required'
                }, status.HTTP_400_BAD_REQUEST
            
            payment_type = data.get('payment_type')
            
            if payment_type == 'ticket_purchase':
                # Only fans can purchase tickets
                if not hasattr(user, 'fan'):
                    return {
                        'detail': 'Only fans can purchase tickets',
                        'code': 'invalid_user_type'
                    }, status.HTTP_403_FORBIDDEN
                return PaymentService._create_ticket_payment_intent(user, data)
            elif payment_type == 'subscription':
                # Only artists and venues can subscribe
                if not hasattr(user, 'artist_profile') and not hasattr(user, 'venue_profile'):
                    return {
                        'detail': 'Only artists and venues can subscribe to plans',
                        'code': 'invalid_user_type'
                    }, status.HTTP_403_FORBIDDEN
                return PaymentService._create_subscription_payment_intent(user, data)
            else:
                return {
                    'detail': 'Invalid payment type. Must be ticket_purchase or subscription',
                    'code': 'invalid_payment_type'
                }, status.HTTP_400_BAD_REQUEST
            
        except stripe.error.StripeError as e:
            logger.error(f'Stripe error creating payment intent: {str(e)}')
            return {'detail': str(e.user_message or str(e))}, status.HTTP_400_BAD_REQUEST
        except Exception as e:
            logger.error(f'Error creating payment intent: {str(e)}', exc_info=True)
            return {'detail': 'An error occurred while processing your payment'}, status.HTTP_500_INTERNAL_SERVER_ERROR
    
    @staticmethod
    def _create_ticket_payment_intent(user, data):
        """
        Create payment intent for mobile ticket purchases with card payment.
        
        Args:
            user: The user making the purchase
            data: {
                tickets: [
                    {
                        gig_id: ID of the gig (required)
                        quantity: Number of tickets (default: 1)
                        ticket_type_id: ID of the ticket type (optional)
                    },
                    ...
                ]
                payment_method_id: Stripe payment method ID (required)
                save_payment_method: Boolean to save card for future use
            }
            
        Returns:
            tuple: (response_data, status_code)
        """
        from gigs.models import Gig  # Local import to avoid circular imports
        
        try:
            # Debug logging
            logger.info(f'Raw data received in _create_ticket_payment_intent: {data}')
            logger.info(f'Data type: {type(data)}')
            logger.info(f'Data keys: {data.keys() if hasattr(data, "keys") else "Not a dictionary"}')
            
            # Handle both 'ticket' and 'tickets' keys for backward compatibility
            tickets = data.get('tickets', data.get('ticket'))
            logger.info(f'Tickets data: {tickets}')
            logger.info(f'Tickets type: {type(tickets) if tickets is not None else "None"}')
            if not tickets or not isinstance(tickets, list) or len(tickets) == 0:
                return {
                    'detail': 'At least one ticket is required',
                    'code': 'tickets_required'
                }, status.HTTP_400_BAD_REQUEST
                
            payment_method_id = data.get('payment_method_id')
            if not payment_method_id:
                return {
                    'detail': 'Payment method ID is required',
                    'code': 'payment_method_required'
                }, status.HTTP_400_BAD_REQUEST
            
            total_amount = 0
            line_items = []
            processed_tickets = []
            
            # First, validate all tickets and collect gig data
            for ticket_data in tickets:
                gig_id = ticket_data.get('gig_id')
                quantity = int(ticket_data.get('quantity', 1))
                
                if not gig_id:
                    return {
                        'detail': 'Gig ID is required for all tickets',
                        'code': 'missing_gig_id'
                    }, status.HTTP_400_BAD_REQUEST
                    
                if quantity < 1:
                    return {
                        'detail': 'Quantity must be at least 1',
                        'code': 'invalid_quantity'
                    }, status.HTTP_400_BAD_REQUEST
                
                # Store ticket data for processing
                processed_tickets.append({
                    'gig_id': gig_id,
                    'quantity': quantity,
                    'ticket_data': ticket_data
                })
            
            with transaction.atomic():
                # Process each ticket in the transaction
                for ticket_info in processed_tickets:
                    gig_id = ticket_info['gig_id']
                    quantity = ticket_info['quantity']
                    ticket_data = ticket_info['ticket_data']
                    
                    # Get gig with lock
                    try:
                        gig = Gig.objects.select_related('created_by', 'venue').select_for_update().get(
                            id=gig_id, 
                            status='approved'
                        )
                    except Gig.DoesNotExist:
                        return {
                            'detail': f'Gig with ID {gig_id} not found or not approved',
                            'code': 'gig_not_found',
                            'gig_id': gig_id
                        }, status.HTTP_404_NOT_FOUND
                    
                    # Check ticket availability
                    if gig.max_tickets is not None:
                        tickets_sold = gig.tickets.count()
                        available_tickets = gig.max_tickets - tickets_sold
                        if available_tickets < quantity:
                            return {
                                'detail': f'Not enough tickets available for gig {gig_id}. Only {available_tickets} ticket(s) left',
                                'code': 'insufficient_tickets',
                                'available': available_tickets,
                                'gig_id': gig_id
                            }, status.HTTP_400_BAD_REQUEST
                    
                    # Calculate amount for this ticket (in cents)
                    ticket_amount = int(gig.ticket_price * 100) * quantity
                    total_amount += ticket_amount
                    
                    # Debug logging
                    logger.info(f'Processing ticket:')
                    logger.info(f'Gig ID: {gig.id}')
                    logger.info(f'Ticket price: ${gig.ticket_price}')
                    logger.info(f'Quantity: {quantity}')
                    logger.info(f'Ticket amount (cents): {ticket_amount}')
                    logger.info(f'Running total (cents): {total_amount}')
                    
                    # Add to line items for metadata
                    line_items.append({
                        'gig_id': str(gig.id),
                        'quantity': quantity,
                        'ticket_type_id': ticket_data.get('ticket_type_id'),
                        'amount': ticket_amount,
                        'price_per_ticket': float(gig.ticket_price)
                    })
                    
                    # Store the gig price for later use
                    ticket_data['price_per_ticket'] = float(gig.ticket_price)
            
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
                
                # Create payment intent for mobile with all tickets
                try:
                    intent = stripe.PaymentIntent.create(
                        amount=total_amount,
                        currency='usd',
                        customer=customer.id,
                        payment_method=payment_method_id,
                        confirm=True,
                        off_session=False,
                        metadata={
                            'user_id': str(user.id),
                            'tickets': json.dumps(line_items),
                            'type': 'ticket_purchase',
                            'platform': 'mobile',
                            'total_tickets': sum(t['quantity'] for t in tickets)
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
                    
                    # Create ticket records in database
                    from .models import Ticket, Payment, PaymentStatus
                    import uuid
                    import time
                    tickets_created = []
                    for ticket_data in tickets:
                        gig = Gig.objects.get(id=ticket_data['gig_id'])
                        ticket_price = gig.ticket_price  # Get price from gig
                        for _ in range(ticket_data['quantity']):
                            # Generate a unique booking code
                            booking_code = f"TKT-{int(time.time())}-{uuid.uuid4().hex[:6].upper()}"
                            ticket = Ticket.objects.create(
                                user=user,
                                gig=gig,
                                price=ticket_price,  # Use the gig's ticket price
                                booking_code=booking_code  # Add unique booking code
                            )
                            tickets_created.append(ticket.id)
                    
                    # Create payment record
                    payment = Payment.objects.create(
                        user=user,
                        payee=gig.created_by,  # The gig creator receives the payment
                        amount=Decimal(total_amount) / 100,  # Convert to dollars
                        status=PaymentStatus.PENDING,
                        payment_intent_id=intent.id,
                        fee=Decimal(0),  # Calculate fee if applicable
                        gig=gig
                    )
                    
                    return {
                        'client_secret': intent.client_secret,
                        'payment_intent_id': intent.id,
                        'payment_id': str(payment.id),
                        'amount': total_amount,
                        'currency': 'usd',
                        'ticket_ids': tickets_created,
                        'requires_action': intent.status == 'requires_action',
                        'status': intent.status
                    }, status.HTTP_200_OK
                    
                except stripe.error.CardError as e:
                    # Log card error and let the transaction roll back
                    logger.error(f'Card error: {str(e)}')
                    # The transaction will be rolled back automatically due to the error
                    # No need to manually update tickets_remaining as we calculate it dynamically
                
                # Create ticket records in database
                from .models import Ticket
                tickets_created = []
                for ticket_data in tickets:
                    for _ in range(ticket_data['quantity']):
                        ticket = Ticket.objects.create(
                            user=user,
                            gig_id=ticket_data['gig_id'],
                            ticket_type_id=ticket_data.get('ticket_type_id'),
                            price=ticket_data['amount'] / 100 / ticket_data['quantity']  # Convert back to dollars per ticket
                        )
                        tickets_created.append(ticket.id)
                
                return {
                    'client_secret': intent.client_secret,
                    'amount': total_amount,
                    'currency': 'usd',
                    'status': intent.status,
                    'ticket_ids': tickets_created,
                    'metadata': {
                        'tickets': line_items,
                        'total_tickets': sum(t['quantity'] for t in tickets)
                    }
                }, status.HTTP_200_OK
                
            except stripe.error.CardError as e:
                logger.error(f'Card error in payment intent: {str(e)}')
                # Refund any reserved tickets
                for ticket_data in tickets:
                    try:
                        gig = Gig.objects.get(id=ticket_data['gig_id'])
                        gig.tickets_remaining += ticket_data['quantity']
                        gig.save(update_fields=['tickets_remaining'])
                    except Exception as refund_error:
                        logger.error(f'Error refunding tickets: {str(refund_error)}')
                
                return {
                    'detail': str(e.user_message) if hasattr(e, 'user_message') else 'Your card was declined',
                    'code': e.code if hasattr(e, 'code') else 'card_error',
                    'decline_code': getattr(e, 'decline_code', None)
                }, status.HTTP_400_BAD_REQUEST
                
            except Exception as e:
                logger.error(f'Error creating payment intent: {str(e)}', exc_info=True)
                # Refund any reserved tickets
                for ticket_data in tickets:
                    try:
                        gig = Gig.objects.get(id=ticket_data['gig_id'])
                        gig.tickets_remaining += ticket_data['quantity']
                        gig.save(update_fields=['tickets_remaining'])
                    except Exception as refund_error:
                        logger.error(f'Error refunding tickets: {str(refund_error)}')
                
                return {
                    'detail': 'An error occurred while processing your payment',
                    'code': 'payment_processing_error'
                }, status.HTTP_500_INTERNAL_SERVER_ERROR
            
        except ValueError as ve:
            logger.error(f'Validation error in ticket purchase: {str(ve)}')
            return {'detail': str(ve)}, status.HTTP_400_BAD_REQUEST
        except Exception as e:
            logger.error(f'Error creating ticket payment intent: {str(e)}', exc_info=True)
            return {'detail': 'Failed to process payment'}, status.HTTP_500_INTERNAL_SERVER_ERROR
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@csrf_exempt
def create_payment_intent(request, gig_id=None):
    # Import models locally to prevent AppRegistryNotReady error
    from .models import PaymentStatus
    """
    Create a payment intent for ticket purchases or subscriptions.
    
    Request format for gig ticket purchase (fans only):
    {
        "payment_type": "ticket_purchase",
        "item_id": 123,  # gig_id can also be passed in the URL
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
    
    The gig_id can be provided either in the URL or in the request body (item_id).
    If both are provided, the one in the request body takes precedence.
    """
    try:
        # Debug logging for incoming request
        logger.info('-' * 50)
        logger.info('Raw request data:')
        logger.info(f'Request data type: {type(request.data)}')
        logger.info(f'Request data content: {request.data}')
        logger.info('-' * 50)
        
        # Make a copy of the request data to avoid modifying the original
        data = request.data.copy()
        
        # Debug logging after copy
        logger.info('After copying request data:')
        logger.info(f'Data type: {type(data)}')
        logger.info(f'Data content: {data}')
        
        # If this is a ticket purchase and gig_id is in URL but not in data, add it to data
        if data.get('payment_type') == 'ticket_purchase' and gig_id and 'item_id' not in data:
            data['item_id'] = str(gig_id)
            logger.info(f'Added gig_id {gig_id} to data as item_id')
            
        response, status_code = PaymentService.create_payment_intent(request.user, data)
        return Response(response, status=status_code)
    except Exception as e:
        logger.error(f'Unexpected error in create_payment_intent: {str(e)}', exc_info=True)
        return Response(
            {'detail': 'An unexpected error occurred while processing your request'},
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
                    'detail': 'Plan ID and payment method ID are required',
                    'code': 'missing_required_fields'
                }, status.HTTP_400_BAD_REQUEST
            
            # Determine if user is artist or venue
            is_artist = hasattr(user, 'artist_profile')
            is_venue = hasattr(user, 'venue_profile')
            
            if not (is_artist or is_venue):
                return {
                    'detail': 'Only artists and venues can subscribe to plans',
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
                    'detail': 'Subscription plan not found',
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
                'detail': e.user_message or 'Card payment failed',
                'code': e.code or 'card_error',
                'decline_code': getattr(e, 'decline_code', None)
            }, status.HTTP_400_BAD_REQUEST
            
        except stripe.error.StripeError as e:
            logger.error(f'Stripe error during subscription: {str(e)}')
            return {
                'detail': str(e.user_message or 'Failed to create subscription'),
                'code': getattr(e, 'code', 'stripe_error'),
                'decline_code': getattr(e, 'decline_code', None)
            }, status.HTTP_400_BAD_REQUEST
            
        except Exception as e:
            logger.error(f'Error in subscription payment intent: {str(e)}', exc_info=True)
            return {
                'detail': 'An error occurred while processing your subscription',
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

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_tickets(request, gig_id=None):
    from gigs.models import Gig
    from payments.models import Ticket
    from django.utils import timezone
    from django.db.models import Count

    user = request.user
    now = timezone.now()

    try:
        if gig_id:
            # Specific gig ticket details
            try:
                gig = Gig.objects.get(id=gig_id, status='approved')
                
                # Get all tickets for this gig and user
                user_tickets = Ticket.objects.filter(
                    gig=gig, 
                    user=user
                ).select_related('gig').order_by('-created_at')
                
                if not user_tickets.exists():
                    return Response(
                        {'detail': 'No tickets found for this gig'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Get the gig details
                # Safely get venue name
                venue_name = None
                if hasattr(gig, 'venue') and gig.venue:
                    if hasattr(gig.venue, 'name'):
                        venue_name = gig.venue.name
                    elif hasattr(gig.venue, 'title'):  # Try 'title' if 'name' doesn't exist
                        venue_name = gig.venue.title
                
                gig_data = {
                    'id': gig.id,
                    'title': gig.title,
                    'banner': request.build_absolute_uri(f"/media/{gig.flyer_image}") if hasattr(gig, 'flyer_image') and gig.flyer_image else None,
                    'event_date': gig.event_date,
                    'venue_name': venue_name,
                    'total_tickets': user_tickets.count(),
                    'tickets': []
                }
                
                # Add ticket details
                for ticket in user_tickets:
                    gig_data['tickets'].append({
                        'ticket_id': ticket.id,
                        'booking_code': ticket.booking_code,
                        'purchase_date': ticket.created_at,
                        'price': str(ticket.price),
                        'is_used': ticket.checked_in
                    })
                
                return Response({
                    'status': 'success',
                    'gig': gig_data
                })
                
            except Gig.DoesNotExist:
                return Response(
                    {'detail': 'Gig not found or not approved'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            # List all gigs with ticket counts for the user
            gigs_with_tickets = Gig.objects.filter(
                tickets__user=user,
                status='approved'
            ).annotate(
                ticket_count=Count('tickets')
            ).distinct()
            
            gigs_data = []
            for gig in gigs_with_tickets:
                # Safely get venue name
                venue_name = None
                if hasattr(gig, 'venue') and gig.venue:
                    if hasattr(gig.venue, 'name'):
                        venue_name = gig.venue.name
                    elif hasattr(gig.venue, 'title'):  # Try 'title' if 'name' doesn't exist
                        venue_name = gig.venue.title
                
                gig_data = {
                    'id': gig.id,
                    'title': gig.title,
                    'banner': request.build_absolute_uri(f"/media/{gig.flyer_image}") if hasattr(gig, 'flyer_image') and gig.flyer_image else None,
                    'event_date': gig.event_date,
                    'venue_name': venue_name,
                    'ticket_count': gig.ticket_count,
                    'is_upcoming': gig.event_date >= now
                }
                gigs_data.append(gig_data)
            
            # Sort by event date (upcoming first, then past events)
            gigs_data.sort(key=lambda x: (1, x['event_date']) if x['is_upcoming'] else (2, -x['event_date'].timestamp()))
            
            return Response({
                'status': 'success',
                'gigs': gigs_data
            })
            
    except Exception as e:
        logger.error(f'Error in list_tickets: {str(e)}')
        return Response(
            {'detail': 'An error occurred while retrieving tickets'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_purchased_tickets_detail(request, gig_id):
    from gigs.models import Gig
    from payments.models import Ticket

    try:
        # Get the gig and verify it exists and is approved
        try:
            gig = Gig.objects.get(id=gig_id, status='approved')
        except Gig.DoesNotExist:
            return Response(
                {'detail': 'Gig not found or not approved'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all tickets for this gig and user
        tickets = Ticket.objects.filter(
            gig=gig,
            user=request.user
        ).select_related('gig__venue', 'gig__created_by')

        if not tickets.exists():
            return Response(
                {'detail': 'No tickets found for this gig'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get all collaborators for the gig
        collaborators = list(gig.collaborators.all().values_list('name', flat=True))
        
        # Safely get venue information
        venue_name = None
        venue_address = None
        if hasattr(gig, 'venue') and gig.venue:
            venue = gig.venue
            venue_name = getattr(venue, 'name', None) or getattr(venue, 'title', 'N/A')
            venue_address = getattr(venue, 'address', 'N/A')
        
        # Prepare ticket data
        tickets_data = []
        for ticket in tickets:
            tickets_data.append({
                'ticket_id': ticket.id,
                'gig_id': gig.id,
                'gig_title': gig.title,
                'gig_date': gig.event_date,
                'location': venue_address,
                'address': venue_address,
                'booking_code': ticket.booking_code,
                'ticket_price': str(gig.ticket_price),
                'purchase_date': ticket.created_at,
                'qr_code_url': request.build_absolute_uri(ticket.qr_code.url) if ticket.qr_code and hasattr(ticket.qr_code, 'url') else None,
                'artist': getattr(gig.created_by, 'name', 'Unknown Artist') if gig.created_by else 'Unknown Artist',
                'collaborators': collaborators,
                'venue_name': venue_name,
                'is_used': getattr(ticket, 'checked_in', False),
                'used_at': getattr(ticket, 'checked_in_at', None)
            })

        # Add gig details that are common to all tickets
        response_data = {
            'gig': {
                'id': gig.id,
                'title': gig.title,
                'event_date': gig.event_date,
                'venue_name': venue_name,
                'venue_address': venue_address,
                'banner': request.build_absolute_uri(str(gig.flyer_image)) if hasattr(gig, 'flyer_image') and gig.flyer_image else None,
                'total_tickets': len(tickets_data)
            },
            'tickets': tickets_data
        }

        return Response(response_data)

    except Exception as e:
        logger.error(f'Error in get_purchased_tickets_detail: {str(e)}')
        return Response(
            {'detail': 'Ticket not found or does not belong to this user.'},
            status=status.HTTP_404_NOT_FOUND
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def capture_payment_intent(request):
    """
    Confirm and/or capture a PaymentIntent (manual or automatic capture).

    Body params:
    ─────────────────────────────────────────────
    payment_intent_id   (str, required)
    payment_method_id   (str, optional) – required if status is `requires_payment_method`
    """

    payment_intent_id = request.data.get('payment_intent_id')
    payment_method_id = request.data.get('payment_method_id')

    if not payment_intent_id:
        return Response({'detail': 'payment_intent_id is required.'}, status=400)

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        if intent.status == 'requires_payment_method':
            if not payment_method_id:
                return Response({
                    'detail': (
                        'This PaymentIntent still needs a payment method. '
                        'Provide payment_method_id or confirm it client‑side.'
                    ),
                    'stripe_status': intent.status
                }, status=400)

            # Confirm with payment method and prevent redirects
            intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id,
                
            )

        elif intent.status == 'requires_confirmation':
            # Confirm without payment_method if one already attached
            intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id
                
            )

        # Only capture if required
        if intent.status == 'requires_capture':
            captured_intent = stripe.PaymentIntent.capture(payment_intent_id)
            return Response({
                'detail': 'Payment captured successfully.',
                'payment_intent': captured_intent
            }, status=200)

        elif intent.status == 'succeeded':
            return Response({'detail': 'PaymentIntent is already captured.'}, status=200)

        else:
            return Response({
                'detail': (
                    f'Cannot capture PaymentIntent in status "{intent.status}". '
                    'Complete payment client-side if needed.'
                ),
                'stripe_status': intent.status
            }, status=400)

    except stripe.error.CardError as e:
        return Response({'detail': str(e.user_message or str(e))}, status=400)

    except stripe.error.InvalidRequestError as e:
        return Response({'detail': f'Stripe error: {str(e)}'}, status=400)

    except Exception as e:
        return Response({'detail': f'Unexpected error: {str(e)}'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def handle_contract_signature(request):
    """
    Handle contract signature payment intent.
    
    This endpoint is called when a contract signature payment intent succeeds.
    It updates the contract status and notifies the involved parties.
    
    Request body:
    {
        "payment_intent_id": "pi_xxx"
    }
    """
    payment_intent_id = request.data.get('payment_intent_id')
    
    if not payment_intent_id:
        return Response({'detail': 'payment_intent_id is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        # Retrieve the payment intent
        payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
        
        # Check if the payment was successful
        if payment_intent.status != 'succeeded':
            return Response({'detail': 'Payment intent not successful'}, status=status.HTTP_400_BAD_REQUEST)
        
        # Handle the contract signature logic here
        # For example, update the contract status in your database
        metadata=payment_intent.get('metadata', {})
        logger.info(f"[Stripe Webhook] Handling contract signature for payment intent {payment_intent_id} with metadata: {metadata}")
        contract_id = metadata['contract_id']
        contract = Contract.objects.get(id=contract_id)
        contract.is_paid = True
        contract.save()
        
        if metadata['is_host'] == 'true':
            contract.artist_signed = True
            contract.artist_signed_at = datetime.datetime.now()
            contract.save()
        else:
            gig = contract.gig
            artist = contract.artist
            if artist.id in gig.invitees.values_list('id', flat=True):
                contract.artist_signed = True
                contract.artist_signed_at = datetime.datetime.now()
                contract.save()
                gig.invitees.remove(artist)
                gig.collaborators.add(artist.id)
                gig.save()
            else:
                contract.collaborator_signed = True
                contract.collaborator_signed_at = datetime.datetime.now()
                contract.save()
                gig.collaborators.add(artist.id)
                gig.save()
        
        return Response({'status': 'success', 'message': 'Contract signature processed successfully'}, status=status.HTTP_200_OK)
    
    except stripe.error.StripeError as e:
        logger.error(f'Stripe error: {str(e)}')
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    except Exception as e:
        logger.error(f'Unexpected error: {str(e)}', exc_info=True)
        return Response({'detail': 'An unexpected error occurred'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)