from django.utils import timezone
from rest_framework import serializers
from .models import Gig, Contract, GigInvite, GigType, GigInviteStatus, Tour
from custom_auth.serializers import UserSerializer
from custom_auth.models import Venue, PerformanceTier
from artists.serializers import ArtistListSerializer


class VenueSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = Venue
        fields = ['id', 'name', 'location', 'address',
                  'capacity', 'artist_capacity', 'city']

    def get_name(self, obj):
        return obj.user.name if obj.user else None


class TourSerializer(serializers.ModelSerializer):
    """Serializer for Tour model"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    gigs_count = serializers.IntegerField(read_only=True)
    cities = serializers.ListField(child=serializers.CharField(), read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Tour
        fields = [
            'id', 'title', 'description', 'artist', 'start_date', 'end_date',
            'status', 'status_display', 'is_featured', 'gigs_count', 'cities',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at', 'artist']
    
    def validate(self, attrs):
        """Validate tour dates"""
        start_date = attrs.get('start_date')
        end_date = attrs.get('end_date')
        
        if start_date and end_date and start_date > end_date:
            raise serializers.ValidationError({
                'end_date': 'End date must be after start date.'
            })
        
        return attrs



class BaseGigSerializer(serializers.ModelSerializer):
    """Base serializer with common functionality for Gig serializers."""
    flyer_image = serializers.SerializerMethodField()
    is_liked = serializers.SerializerMethodField()
    is_part_of_tour = serializers.BooleanField(read_only=True)
    tour = serializers.PrimaryKeyRelatedField(queryset=Tour.objects.all(), required=False, allow_null=True)
    tour_order = serializers.IntegerField(required=False, allow_null=True)
    
    class Meta:
        model = Gig
        fields = [
            'id', 'title', 'description', 'gig_type', 'event_date',
            'booking_start_date', 'booking_end_date', 'flyer_image',
            'minimum_performance_tier', 'max_artists', 'max_tickets', 
            'ticket_price', 'venue_fee', 'status', 'is_public', 'sold_out', 
            'slot_available', 'is_liked', 'is_part_of_tour', 'tour', 'tour_order',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def get_flyer_image(self, obj):
        if obj.flyer_image and hasattr(obj.flyer_image, 'url'):
            return self.context['request'].build_absolute_uri(obj.flyer_image.url)
        return None
    
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False
    
    def validate(self, attrs):
        """Validate gig data based on gig type"""
        gig_type = attrs.get('gig_type', self.instance.gig_type if self.instance else None)
        
        # For tour gigs, ensure they have a tour and are of type TOUR_GIG
        if attrs.get('tour') or (self.instance and self.instance.tour):
            if gig_type != GigType.TOUR_GIG:
                attrs['gig_type'] = GigType.TOUR_GIG
            attrs['is_part_of_tour'] = True
            
            # Ensure tour order is set for tour gigs
            if 'tour_order' not in attrs and (not self.instance or not self.instance.tour_order):
                tour = attrs.get('tour') or (self.instance.tour if self.instance else None)
                if tour:
                    last_order = Gig.objects.filter(tour=tour).aggregate(
                        models.Max('tour_order')
                    )['tour_order__max'] or 0
                    attrs['tour_order'] = last_order + 1
        
        # For non-tour artist gigs, ensure they don't have tour fields
        elif gig_type == GigType.ARTIST_GIG:
            if 'tour' in attrs and attrs['tour'] is not None:
                raise serializers.ValidationError({
                    'tour': 'Cannot assign a tour to a non-tour gig.'
                })
            attrs['is_part_of_tour'] = False
            
        return attrs


class GigSerializer(BaseGigSerializer):
    """Serializer for Gig model with proper field handling and serialization."""
    # Additional computed fields for list view
    flyer_bg = serializers.SerializerMethodField()
    flyer_bg_url = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    max_artist = serializers.SerializerMethodField()
    price_validation = serializers.SerializerMethodField()
    

    class Meta:
        model = Gig
        fields = [
            # Core fields
            'id', 'title', 'description', 'gig_type', 'event_date',
            'booking_start_date', 'booking_end_date', 'flyer_image',
            'flyer_bg', 'flyer_bg_url', 'minimum_performance_tier',
            'max_artists', 'max_tickets', 'ticket_price', 'venue_fee',
            'status', 'is_public', 'sold_out', 'slot_available', 'price_validation',
            'request_message', 'expires_at', 'created_at', 'updated_at',

            # Related fields

            'venue', 'created_by', 
            
            # Tour fields
            'is_part_of_tour', 'tour', 'tour_order',
            

            # Computed fields
            'is_liked', 'user', 'name', 'max_artist'
        ]
        read_only_fields = [
            'id', 'sold_out', 'slot_available', 'created_at',
            'updated_at', 'expires_at',  'is_liked',
            'user', 'name', 'max_artist', 'flyer_image', 'flyer_bg', 'flyer_bg_url'
        ]

    def get_flyer_image(self, obj):
        """Return the URL of the flyer image if it exists."""
        if not obj.flyer_image:
            return None
        try:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.flyer_image.url)
            return str(obj.flyer_image.url)
        except (ValueError, AttributeError):
            return None

    def get_flyer_bg(self, obj):
        """Alias for get_flyer_image for backward compatibility."""
        return self.get_flyer_image(obj)

    def get_flyer_bg_url(self, obj):
        """Alias for get_flyer_image for backward compatibility."""
        return self.get_flyer_image(obj)

    def get_user(self, obj):
        """Return the ID of the user who created the gig."""
        return obj.created_by.id if obj.created_by else None

    def validate(self, attrs):
        """Validate gig data based on gig type"""
        gig_type = attrs.get('gig_type', self.instance.gig_type if self.instance else None)
        
        # For tour gigs, ensure they have a tour and are of type TOUR_GIG
        if attrs.get('tour') or (self.instance and self.instance.tour):
            if gig_type != GigType.TOUR_GIG:
                attrs['gig_type'] = GigType.TOUR_GIG
            attrs['is_part_of_tour'] = True
            
            # Ensure tour order is set for tour gigs
            if 'tour_order' not in attrs and (not self.instance or not self.instance.tour_order):
                tour = attrs.get('tour') or (self.instance.tour if self.instance else None)
                if tour:
                    last_order = Gig.objects.filter(tour=tour).aggregate(
                        models.Max('tour_order')
                    )['tour_order__max'] or 0
                    attrs['tour_order'] = last_order + 1
        
        # For non-tour artist gigs, ensure they don't have tour fields
        elif gig_type == GigType.ARTIST_GIG:
            if 'tour' in attrs and attrs['tour'] is not None:
                raise serializers.ValidationError({
                    'tour': 'Cannot assign a tour to a non-tour gig.'
                })
            attrs['is_part_of_tour'] = False
            attrs['tour'] = None
            attrs['tour_order'] = None
        
        return attrs
    

    def get_name(self, obj):
        """Return the title of the gig as the name (for backward compatibility)."""
        return obj.title

    def get_max_artist(self, obj):
        """Return the max_artists value (for backward compatibility)."""
        return obj.max_artists

    def get_price_validation(self, obj):
        """Return price validation information for the gig."""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user') or not request.user.is_authenticated:
            return None

        # Only include price validation for the gig creator
        if obj.created_by != request.user:
            return None

        # Only for artist gigs
        if obj.gig_type != GigType.ARTIST_GIG:
            return None

        return obj.requires_price_confirmation()

    def get_is_liked(self, obj):
        """Check if the current user has liked this gig."""
        request = self.context.get('request')
        if request and hasattr(request, 'user') and request.user.is_authenticated:
            return obj.likes.filter(id=request.user.id).exists()
        return False

    def to_representation(self, instance):
        """Convert instance to dict, ensuring all data is JSON serializable."""
        data = super().to_representation(instance)

        # Ensure all values are JSON serializable
        for key, value in list(data.items()):
            if isinstance(value, (bytes, bytearray)):
                del data[key]
            elif hasattr(value, 'read'):
                try:
                    data[key] = str(value)
                except (ValueError, AttributeError):
                    del data[key]

        return data

    def create(self, validated_data):
        """Create a new gig with the current user as the creator."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "User must be authenticated to create a gig.")

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

    def update(self, instance, validated_data):
        flyer_bg = self.context['request'].FILES.get('flyer_bg')
        if flyer_bg:
            validated_data['flyer_image'] = flyer_bg
        return super().update(instance, validated_data)


class GigInviteSerializer(serializers.ModelSerializer):
    """
    Serializer for GigInvite model
    """
    gig = serializers.PrimaryKeyRelatedField(queryset=Gig.objects.all())
    user = UserSerializer(read_only=True)
    artist_received = ArtistListSerializer(read_only=True)
    status = serializers.ChoiceField(
        choices=GigInviteStatus.choices, default=GigInviteStatus.PENDING)

    class Meta:
        model = GigInvite
        fields = ['id', 'gig', 'user', 'artist_received',
                  'status', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def validate(self, attrs):
        # Ensure the user is the gig creator or an admin
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            gig = attrs.get('gig')
            if gig and gig.created_by != request.user and not request.user.is_staff:
                raise serializers.ValidationError(
                    "You don't have permission to create an invite for this gig.")
        return attrs


class GigDetailSerializer(BaseGigSerializer):
    """
    Detailed serializer for Gig model with all related fields.
    Extends BaseGigSerializer to include related objects and additional fields.
    """
    likes_count = serializers.SerializerMethodField()
    venue = VenueSerializer(read_only=True)
    created_by = UserSerializer(read_only=True)
    collaborators = UserSerializer(many=True, read_only=True)
    invitees = UserSerializer(many=True, read_only=True)

    class Meta(BaseGigSerializer.Meta):
        fields = BaseGigSerializer.Meta.fields + [
            'likes_count', 'venue', 'created_by', 'collaborators', 'invitees'
        ]

    def get_likes_count(self, obj):
        return obj.likes.count()


class VenueEventSerializer(serializers.ModelSerializer):
    """
    Serializer for venue-created events.
    This is used when a venue creates an event that artists can apply to.
    """
    flyer_image = serializers.ImageField(required=False)
    venue_fee = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False)
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
            raise serializers.ValidationError(
                "Booking start date must be in the future.")

        if 'booking_end_date' in attrs and attrs['booking_end_date'] < now:
            raise serializers.ValidationError(
                "Booking end date must be in the future.")

        if ('booking_start_date' in attrs and 'booking_end_date' in attrs and
                attrs['booking_start_date'] >= attrs['booking_end_date']):
            raise serializers.ValidationError(
                "Booking start date must be before end date.")

        if 'event_date' in attrs and attrs['event_date'] < now:
            raise serializers.ValidationError(
                "Event date must be in the future.")

        return attrs


class ContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contract
        fields = ['id', 'artist', 'venue', 'gig', 'price',
                  'pdf', 'image', 'created_at', 'updated_at']
