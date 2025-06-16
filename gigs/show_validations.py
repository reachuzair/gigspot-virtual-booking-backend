import logging
from datetime import timedelta

from django.db.models import Q, Count
from django.utils import timezone
from geopy.distance import geodesic

logger = logging.getLogger(__name__)


class ShowValidationError(Exception):
    """Custom exception for show validation errors"""
    pass


class ShowValidator:
    """
    Validates show creation against various business rules.
    """
    
    def __init__(self, artist, venue, event_date):
        self.artist = artist
        self.venue = venue
        self.event_date = event_date
    
    def validate_show_creation(self):
        """Run all validations for show creation"""
        self.validate_show_frequency()
        self.validate_geo_proximity()
        self.validate_show_limits()
    
    def validate_show_frequency(self):
        """
        Validate Rule #1: Artists can only create one custom show per city every 15 days.
        """
        from .models import Gig
        
        # Get the city from venue address (assuming address is in format "Street, City, State, ZIP")
        try:
            city = self.venue.address.split(',')[-3].strip()  # Gets the city part from address
        except (AttributeError, IndexError):
            logger.warning(f"Could not parse city from venue address: {self.venue.address}")
            return  # Skip validation if we can't parse the city
        
        # Find shows in the same city within the last 15 days
        fifteen_days_ago = timezone.now() - timedelta(days=15)
        
        existing_shows = Gig.objects.filter(
            created_by=self.artist.user,
            venue__address__icontains=city,
            event_date__gte=fifteen_days_ago,
            event_date__lte=timezone.now()
        ).exclude(venue=self.venue).exists()
        
        if existing_shows:
            raise ShowValidationError(
                "You can only create one show in this city every 15 days. "
                "Please wait until the cooldown period is over or use the 'Plan a Tour' feature."
            )
    
    def validate_geo_proximity(self):
        """
        Validate Rule #2: No more than 2 shows within 25 miles within 14 days.
        """
        from .models import Gig  # Local import to avoid circular imports
        
        # Skip if venue doesn't have location data
        if not self.venue.location or len(self.venue.location) != 2:
            logger.warning(f"Venue {self.venue.id} missing location data")
            return
            
        venue_lat, venue_lng = self.venue.location
        venue_coords = (venue_lat, venue_lng)
        
        # Get the date range (14 days before and after the event date)
        start_date = self.event_date - timedelta(days=14)
        end_date = self.event_date + timedelta(days=14)
        
        # Get all shows by this artist in the date range
        recent_shows = Gig.objects.filter(
            created_by=self.artist.user,
            event_date__range=(start_date, end_date),
            venue__location__isnull=False
        ).exclude(venue=self.venue)
        
        # Count shows within 25 miles
        nearby_show_count = 0
        for show in recent_shows:
            try:
                show_lat, show_lng = show.venue.location
                show_coords = (show_lat, show_lng)
                distance = geodesic(venue_coords, show_coords).miles
                
                if distance <= 25:
                    nearby_show_count += 1
                    
                    if nearby_show_count >= 2:
                        raise ShowValidationError(
                            "You cannot create more than 2 shows within a 25-mile radius "
                            "in a 14-day period. Please use the 'Plan a Tour' feature instead."
                        )
            except (TypeError, ValueError) as e:
                logger.warning(f"Error calculating distance for show {show.id}: {e}")
                continue
    
    def validate_show_limits(self):
        """
        Validate Rule #3: Enforce show limits based on subscription tier.
        """
        from .models import Gig
        from subscriptions.models import Subscription
        
        # Get the artist's active subscription
        try:
            subscription = Subscription.objects.get(
                user=self.artist.user,
                status='active'
            )
            subscription_tier = subscription.plan.tier
        except Subscription.DoesNotExist:
            subscription_tier = 'free'
        
        # Check show limits based on subscription tier
        if subscription_tier == 'free':
            raise ShowValidationError(
                "Free tier users cannot create shows. Please upgrade your subscription."
            )
        elif subscription_tier == 'premium':
            # Count shows in the last 30 days
            thirty_days_ago = timezone.now() - timedelta(days=30)
            show_count = Gig.objects.filter(
                created_by=self.artist.user,
                created_at__gte=thirty_days_ago
            ).count()
            
            if show_count >= 3:
                raise ShowValidationError(
                    "Premium tier is limited to 3 shows per 30 days. "
                    "Please upgrade to a higher tier or wait until your limit resets."
                )


def validate_show_duration(gig):
    """
    Validate Rule #6: Show duration should be limited to one night.
    """
    # If this is a multi-day event at the same venue, it's allowed
    if gig.booking_start_date and gig.booking_end_date:
        if gig.booking_start_date.date() != gig.booking_end_date.date():
            # Check if it's the same venue for all days
            if gig.venue:
                return  # Same venue multi-day is allowed
            else:
                raise ShowValidationError(
                    "Multi-city events require using the 'Plan a Tour' feature. "
                    "Please use the tour planning tool for multi-city shows."
                )
