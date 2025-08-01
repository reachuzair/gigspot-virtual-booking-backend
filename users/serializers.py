from rest_framework import serializers
from custom_auth.models import User, Artist, Venue, Fan
from custom_auth.serializers import UserSerializer
from subscriptions.models import ArtistSubscription


class ArtistProfileSerializer(serializers.ModelSerializer):
    user= UserSerializer(read_only=True)
    likes= serializers.IntegerField(source='likes.count', read_only=True)

    def update(self, instance, validated_data):
        if 'merch_url' in validated_data:
            subscription = ArtistSubscription.objects.filter(artist=instance, status='active').first()
            if not subscription or subscription.plan.subscription_tier.upper() != 'PREMIUM':
                raise serializers.ValidationError({
                    'detail': 'Only premium artists can update merch URL.'
                })

        return super().update(instance, validated_data)
    class Meta:
        model = Artist
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']


class VenueProfileSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Venue
        fields = [
            'id',
            'user',
            'name',
            'verification_docs',
            'location',
            'capacity',
            'amenities',
            'proof_type',
            'proof_document',
            'proof_url',
            'seating_plan',
            'reservation_fee',
            'address',
            'artist_capacity',
            'is_completed',
            'stripe_account_id',
            'stripe_onboarding_completed',
            'created_at',
            'updated_at',
            'phone_number',
            'logo',
            'city',
            'state'
        ]
    def update(self, instance, validated_data):
        # Extract and update user-related field
        name = validated_data.pop('name', None)
        
        # Check if capacity is being updated
        capacity = validated_data.get('capacity')
        print(f"Updating venue - Current capacity: {instance.capacity}, New capacity: {capacity}")
        
        if capacity is not None and capacity != instance.capacity:
            # Get the appropriate tier for the new capacity
            from custom_auth.models import VenueTier
            try:
                print(f"Looking for tier for capacity: {capacity}")
                new_tier = VenueTier.get_tier_for_capacity(capacity)
                print(f"Found tier: {new_tier}")
                if new_tier:
                    print(f"Setting tier to: {new_tier.tier} - {new_tier.get_tier_display()}")
                    instance.tier = new_tier
                else:
                    print("No matching tier found for capacity:", capacity)
                    # Let's see what tiers are available
                    all_tiers = VenueTier.objects.all().order_by('min_capacity')
                    print("Available tiers:")
                    for t in all_tiers:
                        print(f"- {t.tier}: {t.min_capacity} - {t.max_capacity}")
            except Exception as e:
                print(f"Error updating venue tier: {e}")
                import traceback
                traceback.print_exc()

        if name is not None:
            instance.user.name = name
            instance.user.save(update_fields=["name"])

        # Update Venue model fields
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        """Add name and email to the serialized response."""
        rep = super().to_representation(instance)
        rep['name'] = instance.user.name
        rep['email'] = instance.user.email
        return rep


class FanProfileSerializer(serializers.ModelSerializer):
    name = serializers.CharField(write_only=True)
    profileImage = serializers.ImageField(
        source='user.profileImage', allow_null=True, required=False)

    class Meta:
        model = Fan
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']

    def update(self, instance, validated_data):
        # Extract and update user fields from validated_data
        name = validated_data.pop('name', None)

        user = instance.user
        if name:
            user.name = name
        user.save()

        # Update Fan instance fields
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        """Add name and email to response output."""
        rep = super().to_representation(instance)
        rep['name'] = instance.user.name
        return rep
