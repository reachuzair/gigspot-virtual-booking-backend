from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from gigs.models import Gig
from .models import CartItem

# Create your views here.

@api_view(['POST'])
def add_to_cart(request):
    user = request.user
    gig_id = request.data.get('gig_id')
    quantity = request.data.get('quantity', 1)
    
    try:
        gig = Gig.objects.get(id=gig_id)
        cart_item, created = CartItem.objects.get_or_create(user=user, gig=gig)
        cart_item.quantity += quantity
        cart_item.save()
        return Response({'detail': 'Gig added to cart successfully.', 'item': cart_item}, status=status.HTTP_200_OK)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        