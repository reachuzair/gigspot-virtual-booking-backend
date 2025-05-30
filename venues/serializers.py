from rest_framework import serializers
from django.utils import timezone
from .models import Event
from custom_auth.models import PerformanceTier


class EventSerializer(serializers.ModelSerializer):
    artist_tier = serializers.ChoiceField(
        choices=PerformanceTier.choices,
        help_text="Required performance tier for artists to book this event"
    )
    
    class Meta:
        model = Event
        fields = [
            'id', 'title', 'artist_tier', 'flyer_image',
            'max_artists', 'ticket_price', 'max_tickets', 'venue_fee',
            'booking_start', 'booking_end', 'created_at', 'updated_at'
        ]
        read_only_fields = ('id', 'created_at', 'updated_at')
        extra_kwargs = {
            'flyer_image': {'required': False}
        }
    
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if 'flyer_image' in representation and representation['flyer_image']:
            # Ensure we're only using the relative path without the domain
            flyer_path = str(representation['flyer_image'])
            if 'http' in flyer_path:
                # Extract just the path part after the domain
                from urllib.parse import urlparse
                parsed = urlparse(flyer_path)
                flyer_path = parsed.path
                # Remove leading slash if present
                if flyer_path.startswith('/'):
                    flyer_path = flyer_path[1:]
            representation['flyer_image'] = flyer_path
        return representation
    
    def validate_artist_tier(self, value):
        """
        Validate that the artist_tier is one of the allowed choices.
        """
        valid_tiers = [choice[0] for choice in PerformanceTier.choices]
        if value not in valid_tiers:
            raise serializers.ValidationError(
                f"Invalid artist tier. Must be one of: {', '.join(valid_tiers)}"
            )
        return value
    
    def validate_booking_times(self, data):
        """
        Validate that booking_end is after booking_start.
        """
        if 'booking_start' in data and 'booking_end' in data:
            if data['booking_start'] >= data['booking_end']:
                raise serializers.ValidationError(
                    "Booking end time must be after booking start time"
                )
        return data
    
    def validate(self, data):
        """
        Run all validation methods.
        """
        data = self.validate_booking_times(data)
        return data