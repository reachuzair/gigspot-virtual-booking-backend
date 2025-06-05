from django.shortcuts import render
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from gigs.models import Gig
from .models import CartItem
from rest_framework.permissions import IsAuthenticated
from .serializers import CartItemSerializer

# Create your views here.


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_to_cart(request):
    user = request.user
    gig_id = request.data.get('gig_id')
    quantity = request.data.get('quantity', 1)

    try:
        gig = Gig.objects.get(id=gig_id)
        cart_item, created = CartItem.objects.get_or_create(user=user, gig=gig)
        cart_item.quantity += quantity
        cart_item.save()
        serializer = CartItemSerializer(cart_item)
        return Response({'detail': 'Gig added to cart successfully.', 'item': serializer.data}, status=status.HTTP_200_OK)

    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_cart_items(request):
    user = request.user
    cart_items = CartItem.objects.filter(user=user, is_booked=False)
    serializer = CartItemSerializer(cart_items, many=True)
    return Response(serializer.data)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def remove_from_cart(request):
    user = request.user
    gig_id = request.data.get('gig_id')
    try:
        cart_item = CartItem.objects.get(
            user=user, gig=gig_id, is_booked=False)
        cart_item.delete()
        return Response({'detail': 'Gig removed from cart successfully.'}, status=status.HTTP_200_OK)
    except CartItem.DoesNotExist:
        return Response({'detail': 'Gig not found in cart.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_cart_item(request, cart_item_id):
    user = request.user
    quantity = request.data.get('quantity', 1)
    try:
        cart_item = CartItem.objects.get(
            user=user, id=cart_item_id, is_booked=False)
        cart_item.quantity = quantity
        cart_item.save()
        serializer = CartItemSerializer(cart_item)
        return Response({'detail': 'Gig updated in cart successfully.', 'item': serializer.data}, status=status.HTTP_200_OK)

    except CartItem.DoesNotExist:
        return Response({'detail': 'Cart item not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
