from rest_framework import serializers
from .models import Gig
from custom_auth.models import Venue
from django.core.files.storage import default_storage

class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ['id']

class GigSerializer(serializers.ModelSerializer):
    venue = VenueSerializer()
    flyer_bg_url = serializers.SerializerMethodField()

    class Meta:
        model = Gig
        fields = [
            'id',
            'name',
            'startDate',
            'endDate',
            'description',
            'venue',
            'max_artist',
            'flyer_bg',
            'flyer_bg_url',
            'is_live',
            'flyer_text',
            'created_at',
            'updated_at'
        ]
        extra_kwargs = {
            'flyer_bg': {'write_only': True},
            'venue': {'required': True}
        }

    def get_flyer_bg_url(self, obj):
        if obj.flyer_bg:
            return obj.flyer_bg.url
        return None

    def create(self, validated_data):
        venue_data = validated_data.pop('venue')
        venue = Venue.objects.get(**venue_data)
        gig = Gig.objects.create(venue=venue, **validated_data)
        return gig