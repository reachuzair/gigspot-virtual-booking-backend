# serializers.py
from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import (
    SubscriptionPlan, ArtistSubscription,
    VenueAdPlan, VenueSubscription
)

class SubscriptionPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubscriptionPlan
        fields = ['id', 'subscription_tier', 'price', 'billing_interval', 'features']

class ArtistSubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    
    class Meta:
        model = ArtistSubscription
        fields = ['id', 'plan', 'status', 'current_period_end', 'cancel_at_period_end']


class VenueAdPlanSerializer(serializers.ModelSerializer):
    """Serializer for venue ad plans"""
    class Meta:
        model = VenueAdPlan
        fields = [
            'id', 'name', 'description', 'weekly_price', 'monthly_price',
            'features', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']


class VenueSubscriptionSerializer(serializers.ModelSerializer):
    """Serializer for venue subscriptions"""
    plan = VenueAdPlanSerializer(read_only=True)
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=VenueAdPlan.objects.filter(is_active=True),
        source='plan',
        write_only=True
    )
    
    class Meta:
        model = VenueSubscription
        fields = [
            'id', 'venue', 'plan', 'plan_id', 'status', 'billing_interval',
            'current_period_start', 'current_period_end', 'cancel_at_period_end',
            'stripe_subscription_id', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'status', 'current_period_start', 'current_period_end',
            'stripe_subscription_id', 'created_at', 'updated_at', 'venue'
        ]

    def validate(self, attrs):
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            # Ensure the venue belongs to the requesting user
            venue = attrs.get('venue')
            if venue and venue.user != request.user:
                raise serializers.ValidationError(
                    "You don't have permission to manage this venue's subscriptions."
                )
        return attrs


class CreateVenueSubscriptionSerializer(serializers.Serializer):
    """Serializer for creating a new venue subscription"""
    plan_id = serializers.PrimaryKeyRelatedField(
        queryset=VenueAdPlan.objects.filter(is_active=True)
    )
    billing_interval = serializers.ChoiceField(
        choices=VenueSubscription.BILLING_INTERVAL,
        default='month'
    )
    payment_method_id = serializers.CharField(required=False)
    
    def create(self, validated_data):
        request = self.context.get('request')
        venue = validated_data['venue']
        plan = validated_data['plan_id']
        billing_interval = validated_data['billing_interval']
        
        # Check for existing active subscription
        existing_sub = VenueSubscription.objects.filter(
            venue=venue,
            status='active',
            current_period_end__gt=timezone.now()
        ).exists()
        
        if existing_sub:
            raise serializers.ValidationError(
                'This venue already has an active subscription.'
            )
        
        # In a real implementation, you would create a Stripe subscription here
        # For now, we'll create a subscription with a test Stripe ID
        subscription = VenueSubscription.objects.create(
            venue=venue,
            plan=plan,
            billing_interval=billing_interval,
            status='active',
            stripe_subscription_id=f'sub_test_{timezone.now().timestamp()}',
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30)
        )
        
        return subscription