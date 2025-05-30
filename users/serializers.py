from rest_framework import serializers
from custom_auth.models import User, Artist, Venue, Fan
class ArtistProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']


class VenueProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']


class FanProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Fan
        fields = '__all__'
        read_only_fields = ['user', 'created_at', 'updated_at']