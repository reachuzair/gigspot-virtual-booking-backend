from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import ROLE_CHOICES, Artist, Venue
from rest_framework.decorators import api_view
from .models import Payment, PaymentStatus
from django.db.models import Sum

# Create your views here.

@api_view(['GET'])
def fetch_balance(request):
    user = request.user
    if user.role != ROLE_CHOICES.ARTIST and user.role != ROLE_CHOICES.VENUE:
        return Response({"detail": "Unauthorized"}, status=status.HTTP_403_FORBIDDEN)
    
    balance = Payment.objects.filter(user=user, status=PaymentStatus.COMPLETED).aggregate(total_balance=Sum('amount'))['total_balance']
    return Response({"balance": balance})
    
    