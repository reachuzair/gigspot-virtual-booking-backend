from rest_framework import serializers
from custom_auth.models import User, Artist, Venue, Fan
from custom_auth.serializers import UserSerializer


class ArtistProfileSerializer(serializers.ModelSerializer):
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
