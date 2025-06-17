from rest_framework import serializers

from gigs.serializers import GigSerializer
from .models import CartItem

class CartItemSerializer(serializers.ModelSerializer):
    gig = GigSerializer(read_only=True)
    class Meta:
        model = CartItem
        fields = '__all__'