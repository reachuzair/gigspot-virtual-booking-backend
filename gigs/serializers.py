from rest_framework import serializers
from .models import Gig, Contract
from custom_auth.models import Venue
from django.core.files.storage import default_storage

class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ['id']

class GigSerializer(serializers.ModelSerializer):
    venue = VenueSerializer(read_only=True)
    flyer_bg_url = serializers.SerializerMethodField()
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Gig
        fields = [
            'id',
            'name',
            'booking_start_date',
            'booking_end_date',
            'event_date',
            'description',
            'user',
            'venue',
            'is_public',
            'max_artist',
            'max_tickets',
            'ticket_price',
            'genre',
            'minimum_performance_tier',
            'request_message',
            'flyer_bg',
            'flyer_bg_url',
            'is_approved',
            'created_at',
            'updated_at',
        ]
        extra_kwargs = {
            'flyer_bg': {'write_only': True},
        }

    def get_flyer_bg_url(self, obj):
        if obj.flyer_bg:
            return obj.flyer_bg.url
        return None

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user if request else None
        gig = Gig.objects.create(user=user, **validated_data)
        return gig


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'artist', 'venue', 'gig', 'price', 'pdf', 'image', 'created_at', 'updated_at']