from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import ROLE_CHOICES, Artist, Venue
from rest_framework.decorators import api_view, permission_classes
from .models import Payment, PaymentStatus
from django.db.models import Sum
from gigs.models import Gig
from rest_framework.permissions import IsAuthenticated

# Create your views here.

@api_view(['GET'])
def fetch_balance(request):
    user = request.user
    if user.role != ROLE_CHOICES.ARTIST and user.role != ROLE_CHOICES.VENUE:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
    
    balance = Payment.objects.filter(user=user, status=PaymentStatus.COMPLETED).aggregate(total_balance=Sum('amount'))['total_balance']
    return Response({"balance": balance})
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def purchase_gig_ticket(request, gig_id):
    user = request.user
    
    if user.role != ROLE_CHOICES.FAN:
        return Response({'detail': 'Please login with fan account.'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        gig = Gig.objects.get(id=gig_id)
        quantity = int(request.data.get('quantity', 1))
        artist_id = int(request.data.get('supporting_artist_id', 0))
        
        if artist_id == 0:
            artist_id = gig.artist.id

        try:
            artist = Artist.objects.get(id=artist_id)
        except Artist.DoesNotExist:
            return Response({'detail': 'Artist not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        # Calculate amounts
        amount = gig.ticket_price * quantity * 100  # in cents
        application_fee = int(amount * 0.1)  # 10% platform fee
        
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
                "quantity": quantity
            }
        )
        
        return Response({
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id
        })
        
    except Gig.DoesNotExist:
        return Response({"error": "Gig not found"}, status=404) 