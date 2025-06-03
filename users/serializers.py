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

    class Meta:
        model = Venue
        fields = [
            'id', 'verification_docs', 'location', 'capacity', 'amenities',
            'seating_plan', 'reservation_fee', 'artist_capacity', 'is_completed',
            'stripe_account_id', 'stripe_onboarding_completed', 'created_at',
            'updated_at', 'user', 'address'
        ]


class FanProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fan
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']
