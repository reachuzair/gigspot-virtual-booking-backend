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
        application_fee = int(request.data.get('application_fee', 0))
        item_id = int(request.data.get('item_id', 0))

        if item_id == 0:
            return Response(
                {'detail': 'Cart item not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # If no specific artist is provided, use the gig's artist
        if artist_id == 0:
            artist = gig.user.artist
            if not artist:
                return Response(
                    {'detail': 'Artist not found for this gig.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            artist_id = artist.id
        else:
            try:
                artist = Artist.objects.get(id=artist_id)
            except Artist.DoesNotExist:
                return Response(
                    {'detail': 'Artist not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Calculate amounts (in cents)
        amount = int(gig.ticket_price * quantity * 100)
        application_fee = int(application_fee * 100)

        # Create the payment intent
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            application_fee_amount=application_fee,
            transfer_data={
                "destination": artist.stripe_account_id,
            },
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


