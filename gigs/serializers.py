from rest_framework import serializers
from django.utils import timezone
from django.core.files.storage import default_storage

from .models import Gig, Contract, GigInvite, GigType, Status, GigInviteStatus
from users.serializers import VenueProfileSerializer, UserSerializer
from custom_auth.models import Artist, Venue, User, PerformanceTier

class VenueSerializer(serializers.ModelSerializer):
    class Meta:
        model = Venue
        fields = ['id', 'name', 'location']

class ArtistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = ['id', 'stage_name', 'profile_image']

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'name', 'role', 'profileImage']
        read_only_fields = ['id', 'email', 'name', 'role', 'profileImage']

class GigSerializer(serializers.ModelSerializer):
    flyer_image_url = serializers.SerializerMethodField()
    venue_details = VenueSerializer(source='venue', read_only=True)
    collaborators_details = UserSerializer(many=True, source='collaborators', read_only=True)
    
    # Backward compatibility fields
    flyer_bg = serializers.ImageField(write_only=True, required=False)
    flyer_bg_url = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    is_approved = serializers.BooleanField(read_only=True)
    max_artist = serializers.IntegerField(required=False, source='max_artists')
    name = serializers.CharField(source='title', required=False)
    artist_tier = serializers.CharField(source='minimum_performance_tier', required=False)

    class Meta:
        model = Gig
        fields = [
            'id', 'title', 'description', 'gig_type',
            'event_date', 'booking_start_date', 'booking_end_date',
            'flyer_image', 'flyer_image_url', 'created_by', 'venue', 'venue_details',
            'minimum_performance_tier', 'artist_tier', 'max_artists', 'max_artists', 'max_tickets',
            'ticket_price', 'venue_fee', 'status', 'is_public',
            'sold_out', 'slot_available', 'request_message',
            'collaborators', 'collaborators_details', 'expires_at',
            'created_at', 'updated_at',
            # Backward compatibility fields
            'flyer_bg', 'flyer_bg_url', 'user', 'is_approved', 'max_artist', 'name'
        ]
        read_only_fields = ['status', 'sold_out', 'slot_available', 'created_at', 'updated_at']
        extra_kwargs = {
            'flyer_image': {'write_only': True, 'required': False},
            'collaborators': {'write_only': True, 'required': False},
            'minimum_performance_tier': {'required': False},
            'max_artists': {'required': False},
            'max_tickets': {'required': False},
        }

    def get_flyer_image_url(self, obj):
        if obj.flyer_image:
            return obj.flyer_image.url
        return None
        
    # Backward compatibility methods
    def get_flyer_bg_url(self, obj):
        return self.get_flyer_image_url(obj)
        
    def get_user(self, obj):
        return obj.created_by.id if obj.created_by else None

    def create(self, validated_data):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("User must be authenticated to create a gig.")
            
        # Handle backward compatibility for flyer_bg
        flyer_bg = validated_data.pop('flyer_bg', None)
        if flyer_bg:
            validated_data['flyer_image'] = flyer_bg
            
        # Set created_by to the current user
        validated_data['created_by'] = request.user
        
        # For venue gigs, set the venue to the user's venue
        if validated_data.get('gig_type') == GigType.VENUE_GIG and hasattr(request.user, 'venue'):
            validated_data['venue'] = request.user.venue
        
        return super().create(validated_data)


class GigInviteSerializer(serializers.ModelSerializer):
    """
    Serializer for GigInvite model
    """
    gig = serializers.PrimaryKeyRelatedField(queryset=Gig.objects.all())
    user = UserSerializer(read_only=True)
    artist_received = ArtistSerializer(read_only=True)
    status = serializers.ChoiceField(choices=GigInviteStatus.choices, default=GigInviteStatus.PENDING)
    
    class Meta:
        model = GigInvite
        fields = ['id', 'gig', 'user', 'artist_received', 'status', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']
    
    def validate(self, attrs):
        # Ensure the user is the gig creator or an admin
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            gig = attrs.get('gig')
            if gig and gig.created_by != request.user and not request.user.is_staff:
                raise serializers.ValidationError("You don't have permission to create an invite for this gig.")
        return attrs


class GigDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Gig model with all related fields
    """
    likes_count = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    venue = VenueProfileSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    collaborators = UserSerializer(many=True, read_only=True)
    invitees = UserSerializer(many=True, read_only=True)
    
    class Meta:
        model = Gig
        fields = [
            'id', 'title', 'description', 'event_date', 'booking_start_date', 
            'booking_end_date', 'flyer_image', 'minimum_performance_tier', 
            'max_artists', 'max_tickets', 'ticket_price', 'venue_fee', 
            'status', 'gig_type', 'is_public', 'sold_out', 'slot_available',
            'likes_count', 'is_liked', 'venue', 'created_by', 'collaborators',
            'invitees', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_likes_count(self, obj):
        return obj.likes.count()
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False


class VenueEventSerializer(serializers.ModelSerializer):
    """
    Serializer for venue-created events.
    This is used when a venue creates an event that artists can apply to.
    """
    flyer_image = serializers.ImageField(required=False)
    venue_fee = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    max_artists = serializers.IntegerField(required=True, min_value=1)
    max_tickets = serializers.IntegerField(required=True, min_value=1)
    minimum_performance_tier = serializers.ChoiceField(
        choices=PerformanceTier.choices,
        required=False
    )
    
    class Meta:
        model = Gig
        fields = [
            'title', 'description', 'event_date', 'booking_start_date', 'booking_end_date',
            'flyer_image', 'minimum_performance_tier', 'max_artists', 'max_tickets',
            'ticket_price', 'venue_fee', 'is_public'
        ]
        extra_kwargs = {
            'is_public': {'default': True}
        }
    
    def validate(self, attrs):
        """
        Validate that booking dates are valid and in the future.
        """
        now = timezone.now()
        
        if 'booking_start_date' in attrs and attrs['booking_start_date'] < now:
            raise serializers.ValidationError("Booking start date must be in the future.")
            
        if 'booking_end_date' in attrs and attrs['booking_end_date'] < now:
            raise serializers.ValidationError("Booking end date must be in the future.")
            
        if ('booking_start_date' in attrs and 'booking_end_date' in attrs and 
            attrs['booking_start_date'] >= attrs['booking_end_date']):
            raise serializers.ValidationError("Booking start date must be before end date.")
            
        if 'event_date' in attrs and attrs['event_date'] < now:
            raise serializers.ValidationError("Event date must be in the future.")
            
        return attrs


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'artist', 'venue', 'gig', 'price', 'pdf', 'image', 'created_at', 'updated_at']