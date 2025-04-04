# serializers.py
from rest_framework import serializers
from .models import SubscriptionPlan, ArtistSubscription

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'subscription_tier', 'price', 'billing_interval', 'features']

class ArtistSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = ArtistSubscription
        fields = ['id', 'plan', 'status', 'current_period_end', 'cancel_at_period_end']