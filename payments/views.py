from decimal import ROUND_HALF_UP, Decimal
import logging
import stripe
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from custom_auth.models import Artist
from gigs.models import Gig
from payments.models import Ticket

# Set up logging
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_payment_intent(request, gig_id):
    """
    Create a payment intent for purchasing tickets to a gig.
    """
    user = request.user
    print(f"User: {user}, Role: {user.role}")
    if user.role != 'fan':  # Assuming ROLE_CHOICES.FAN is 'FAN'
        return Response(
            {'detail': 'Please login with fan account.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        gig = Gig.objects.get(id=gig_id)
        quantity = int(request.data.get('quantity', 1))
        artist_id = int(request.data.get('supporting_artist_id', 0))
        application_fee_input = request.data.get('application_fee', 0)
        item_id = int(request.data.get('item_id', 0))

        if item_id == 0:
            return Response({"detail": "Cart item not found."}, status=status.HTTP_404_NOT_FOUND)

        if artist_id == 0:
            artist = gig.user_id
            if not artist:
                return Response({"detail": "Artist not found for this gig."}, status=status.HTTP_404_NOT_FOUND)
            artist_id = artist.id
        else:
            artist = Artist.objects.get(user_id=artist_id)

        ticket_price = Decimal(str(gig.ticket_price))
        # print(
        #     f"quantity: {quantity} (type: {type(quantity)}), ticket_price: {ticket_price} (type: {type(ticket_price)})")
        application_fee_val = Decimal(str(application_fee_input))

        if quantity <= 0 or ticket_price <= 0:
            return Response({"detail": "Invalid quantity or ticket price."}, status=status.HTTP_400_BAD_REQUEST)

        amount = int((ticket_price * quantity *
                     100).to_integral_value(rounding=ROUND_HALF_UP))
        application_fee = int(
            (application_fee_val * 100).to_integral_value(rounding=ROUND_HALF_UP))

        if amount < 50:
            return Response({"detail": "Total amount must be at least $0.50."}, status=status.HTTP_400_BAD_REQUEST)

        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            application_fee_amount=application_fee,
            transfer_data={"destination": artist.stripe_account_id},
            metadata={
                "gig_id": gig.id,
                "fan_id": user.id,
                "quantity": quantity,
                "payment_intent_for": "ticket_purchase",
                "supporting_artist_id": artist_id,
                "item_id": item_id,
            }
        )
        return Response({
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id
        })

    except Gig.DoesNotExist:
        return Response(
            {"error": "Gig not found"},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Error creating payment intent: {str(e)}")
        return Response(
            {'detail': 'An error occurred while creating the payment intent.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_tickets(request, gig_id):
    """
    List all tickets for a specific gig for the authenticated user.
    """
    try:
        # Get the gig
        gig = Gig.objects.get(id=gig_id)

        # Get tickets for this user and gig
        tickets = Ticket.objects.filter(
            gig=gig,
            user=request.user
        )

        # Serialize the tickets
        ticket_data = [
            {
                'id': ticket.id,
                'gig_id': ticket.gig.id,
                'gig_title': ticket.gig.title,
                'purchase_date': ticket.purchase_date,
                'status': ticket.status,
                'ticket_type': ticket.ticket_type,
                'price': ticket.price,
                'qr_code': ticket.qr_code.url if ticket.qr_code else None
            }
            for ticket in tickets
        ]

        return Response({
            'count': len(ticket_data),
            'tickets': ticket_data
        })

    except Gig.DoesNotExist:
        return Response(
            {'detail': 'Gig not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f'Error listing tickets: {str(e)}')
        return Response(
            {'detail': 'An error occurred while fetching tickets.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )




@api_view(['POST'])
@permission_classes([IsAuthenticated])
def capture_payment_intent(request):
    """
    Capture a PaymentIntent that was created with `capture_method="manual"`.

    Body params:
    ─────────────────────────────────────────────
    payment_intent_id   (str, required)
    payment_method_id   (str, optional) – only needed if the PI is still waiting
                                           for a payment method / confirmation
    """

    payment_intent_id = request.data.get('payment_intent_id')
    payment_method_id = request.data.get('payment_method_id')  # Optional, only needed if the PI is still waiting for a payment method

    if not payment_intent_id:
        return Response(
            {'detail': 'payment_intent_id is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        intent = stripe.PaymentIntent.retrieve(payment_intent_id)

        if intent.status == 'requires_payment_method':
            if not payment_method_id:
                return Response(
                    {
                        'detail': (
                            'This PaymentIntent still needs a payment method. '
                            'Provide payment_method_id or confirm it client‑side '
                            'before capturing.'
                        ),
                        'stripe_status': intent.status
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            intent = stripe.PaymentIntent.confirm(
                payment_intent_id,
                payment_method=payment_method_id
            )

            if intent.status != 'requires_capture':
                return Response(
                    {
                        'detail': f'Unable to capture – PI now has status {intent.status}.',
                        'stripe_status': intent.status
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif intent.status == 'requires_confirmation':
            intent = stripe.PaymentIntent.confirm(payment_intent_id)

            if intent.status != 'requires_capture':
                return Response(
                    {
                        'detail': f'Unable to capture – PI now has status {intent.status}.',
                        'stripe_status': intent.status
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

        elif intent.status == 'requires_capture':
            pass

        elif intent.status == 'succeeded':
            return Response(
                {'detail': 'PaymentIntent is already captured.'},
                status=status.HTTP_200_OK
            )
        else:
            return Response(
                {
                    'detail': (
                        f'Cannot capture PaymentIntent in status "{intent.status}". '
                        'Complete payment on the client first.'
                    ),
                    'stripe_status': intent.status
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        captured_intent = stripe.PaymentIntent.capture(payment_intent_id)

        return Response(
            {
                'detail': 'Payment captured successfully.',
                'payment_intent': captured_intent
            },
            status=status.HTTP_200_OK
        )

    except stripe.error.InvalidRequestError as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

