from rest_framework import serializers

from custom_auth.serializers import VenueSerializer
from .models import TourVenueSuggestion, Tour
from custom_auth.models import Venue, Artist

class TourSerializer(serializers.ModelSerializer):
    """Serializer for Tour model"""
    class Meta:
        model = Tour
        fields = [
            'id', 'description',
            'selected_cities', 'selected_states', 'driving_range_km',
            'vehicle_type', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'status']
        extra_kwargs = {
            # 'start_date': {'required': True},
            # 'end_date': {'required': True},
        }

    # def validate(self, data):
    #     """Validate that start_date is before end_date"""
    #     if data['start_date'] > data['end_date']:
    #         raise serializers.ValidationError("End date must be after start date")
    #     return data


# class VenueSerializer(serializers.ModelSerializer):
#     """Serializer for Venue model in the context of tour planning"""
#     name = serializers.SerializerMethodField()
#     class Meta:
#         model = Venue
#         fields = [
#             'id', 'name', 'city', 'state', 'address', 
#             'capacity', 'venue_type', 'description',
#             'profile_image', 'cover_image', 'is_active'
#         ]
#         read_only_fields = fields
#     def get_name(self, obj):
#         return obj.user.name if hasattr(obj, 'user') and obj.user else ""
    

class TourVenueSuggestionSerializer(serializers.ModelSerializer):
    """Serializer for TourVenueSuggestion model"""
    venue = VenueSerializer(read_only=True)
    
    class Meta:
        model = TourVenueSuggestion
        fields = [
            'id', 'venue', 'event_date','order', 'is_booked',
            'created_at', 'updated_at'
        ]
        read_only_fields = fields

class BookedVenueSerializer(serializers.ModelSerializer):
    """Serializer for booked venues in a tour"""
    venue = VenueSerializer()
    
    class Meta:
        model = TourVenueSuggestion
        fields = [
            'id', 'venue',  'created_at'
        ]
        read_only_fields = fields
