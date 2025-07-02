from datetime import timedelta
from django.utils import timezone
from rest_framework import serializers
from custom_auth.models import Artist, ArtistMonthlyMetrics
from gigs.models import Gig

class BaseArtistSerializer(serializers.ModelSerializer):
    """Base serializer for Artist model with common fields and methods."""
    userId = serializers.IntegerField(source='user.id', read_only=True)
    artistName = serializers.CharField(source='user.name', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    bannerImage = serializers.ImageField(source='logo', read_only=True)
    likes = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Artist
        fields = [
            'id', 'userId', 'artistName', 'createdAt', 'updatedAt',
            'bannerImage', 'likes', 'performance_tier', 'is_verified'
        ]
        read_only_fields = fields
    
    def get_likes(self, obj):
        return obj.likes.count()


class ArtistListSerializer(BaseArtistSerializer):
    """Lightweight serializer for listing artists with basic information."""
    artistGenre = serializers.SerializerMethodField(read_only=True)
    
    class Meta(BaseArtistSerializer.Meta):
        fields = BaseArtistSerializer.Meta.fields + ['artistGenre']
    
    def get_artistGenre(self, obj):
        # Cache the genre on the instance to avoid multiple queries
        if not hasattr(obj, '_cached_genre'):
            gig = Gig.objects.filter(collaborators=obj.user).first()
            obj._cached_genre = gig.details.get('genre') if gig and gig.details else None
        return obj._cached_genre


class ArtistDetailSerializer(BaseArtistSerializer):
    """Detailed serializer for artist profile with comprehensive information."""
    artistGenre = serializers.SerializerMethodField(read_only=True)
    social_links = serializers.SerializerMethodField()
    stats = serializers.SerializerMethodField()
    
    class Meta(BaseArtistSerializer.Meta):
        fields = BaseArtistSerializer.Meta.fields + [
            'artistGenre', 'bio', 'social_links', 'stats',
            'website', 'location', 'genres', 'influences'
        ]
    
    def get_artistGenre(self, obj):
        # More detailed genre handling for the detail view
        gig = Gig.objects.filter(collaborators=obj.user).first()
        if not gig:
            return None
        return gig.details.get('genre') if gig.details else None
    
    def get_social_links(self, obj):
        return {
            'facebook': obj.facebook_url,
            'twitter': obj.twitter_handle,
            'instagram': obj.instagram_handle,
            'youtube': obj.youtube_channel,
            'spotify': obj.spotify_uri,
            'soundcloud': obj.soundcloud_username,
            'apple_music': obj.apple_music_url
        }
    
    def get_stats(self, obj):
        return {
            'total_gigs': Gig.objects.filter(collaborators=obj.user).count(),
            'upcoming_gigs': Gig.objects.filter(
                collaborators=obj.user,
                event_date__gte=timezone.now()
            ).count(),
            'followers': obj.followers.count(),
            'following': obj.user.following.count()
        }


class ArtistAnalyticsSerializer(BaseArtistSerializer):
    """
    Serializer for artist analytics data.
    Returns the four key metrics as percentages (0-100) with historical data.
    """
    current = serializers.SerializerMethodField()
    historical = serializers.SerializerMethodField()

    class Meta(BaseArtistSerializer.Meta):
        fields = ['current', 'historical']
    
    def get_current(self, obj):
        """Get current metrics"""
        return {
            'fan_engagement': round(float(getattr(obj, 'fan_engagement_pct', 0)), 1),
            'social_following': round(float(getattr(obj, 'social_following_pct', 0)), 1),
            'playlist_views': round(float(getattr(obj, 'playlist_views_pct', 0)), 1),
            'buzz_score': round(float(getattr(obj, 'buzz_score_pct', 0)), 1),
            'last_updated': obj.last_metrics_update
        }
    
    def get_historical(self, obj):
        """Get historical monthly metrics for the past 12 months"""
        # Calculate date range
        end_date = timezone.now().replace(day=1)
        start_date = (end_date - timedelta(days=365)).replace(day=1)
        
        # Get all metrics for this date range
        metrics = ArtistMonthlyMetrics.objects.filter(
            artist=obj,
            month__gte=start_date,
            month__lte=end_date
        ).order_by('month')
        
        # Create a list of all months in the range
        months = []
        current = start_date
        while current <= end_date:
            months.append(current)
            # Move to first day of next month
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)
        
        # Create a dict of month -> metrics for easy lookup
        metrics_dict = {m.month.strftime('%Y-%m-01'): m for m in metrics}
        
        # Build the historical data array
        historical_data = []
        for month in months:
            month_key = month.strftime('%Y-%m-01')
            if month_key in metrics_dict:
                m = metrics_dict[month_key]
                historical_data.append({
                    'month': month.strftime('%Y-%m'),
                    'fan_engagement': round(float(m.fan_engagement_pct or 0), 1),
                    'social_following': round(float(m.social_following_pct or 0), 1),
                    'playlist_views': round(float(m.playlist_views_pct or 0), 1),
                    'buzz_score': round(float(m.buzz_score_pct or 0), 1)
                })
            else:
                # If no data for this month, use zeros or previous value
                prev_value = historical_data[-1] if historical_data else None
                historical_data.append({
                    'month': month.strftime('%Y-%m'),
                    'fan_engagement': prev_value['fan_engagement'] if prev_value else 0,
                    'social_following': prev_value['social_following'] if prev_value else 0,
                    'playlist_views': prev_value['playlist_views'] if prev_value else 0,
                    'buzz_score': prev_value['buzz_score'] if prev_value else 0
                })
        
        return historical_data