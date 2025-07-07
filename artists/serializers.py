from datetime import datetime, timedelta
import logging
from rest_framework import serializers
from custom_auth.models import Artist, ArtistMonthlyMetrics
from gigs.models import Gig
from django.db.models import Max
from django.utils import timezone

error_logger = logging.getLogger('error_logger')

class ArtistSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id', read_only=True)
    artistName = serializers.CharField(source='user.name', read_only=True)
    artistGenre = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    bannerImage = serializers.ImageField(source='logo', read_only=True)
    likes = serializers.IntegerField(source='likes.count', read_only=True)
    is_liked = serializers.SerializerMethodField()

    def get_artistGenre(self, obj):
        # Get the first gig for this artist
        gig = Gig.objects.filter(collaborators=obj.user).first()
        if not gig:
            return None
            
        # Return genre from details JSON field if available
        return gig.details.get('genre') if gig.details else None
    def get_is_liked(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return obj.likes.filter(id=request.user.id).exists()
    
    class Meta:
        model = Artist
        fields = [
            'id', 'userId', 'artistName', 'createdAt', 'updatedAt', 'bannerImage','artistGenre','likes','is_liked','stripe_account_id'
        ]
        extra_kwargs = {field: {'required': True} for field in fields if field != 'id'}


class ArtistAnalyticsSerializer(serializers.ModelSerializer):
    """
    Serializer for artist analytics data.
    Returns the four key metrics as percentages (0-100) with historical data.
    """
    current = serializers.SerializerMethodField()
    historical = serializers.SerializerMethodField()

    class Meta:
        model = Artist
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
        end_date = timezone.now().replace(day=1)
        start_date = (end_date - timedelta(days=365)).replace(day=1)

        metrics = ArtistMonthlyMetrics.objects.filter(
            artist=obj,
            month__gte=start_date,
            month__lte=end_date
        ).order_by('month')

        months = []
        current = start_date
        while current <= end_date:
            months.append(current)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1, day=1)
            else:
                current = current.replace(month=current.month + 1, day=1)

        metrics_dict = {m.month.strftime('%Y-%m-01'): m for m in metrics}

        historical_data = []
        for month in months:
            month_key = month.strftime('%Y-%m-01')
            label = month.strftime('%B %Y')  # e.g., "July 2024"

            if month_key in metrics_dict:
                m = metrics_dict[month_key]
                historical_data.append({
                    'month': label,
                    'fan_engagement': round(float(m.fan_engagement_pct or 0), 1),
                    'social_following': round(float(m.social_following_pct or 0), 1),
                    'playlist_views': round(float(m.playlist_views_pct or 0), 1),
                    'buzz_score': round(float(m.buzz_score_pct or 0), 1)
                })
            else:
                prev_value = historical_data[-1] if historical_data else None
                historical_data.append({
                    'month': label,
                    'fan_engagement': prev_value['fan_engagement'] if prev_value else 0,
                    'social_following': prev_value['social_following'] if prev_value else 0,
                    'playlist_views': prev_value['playlist_views'] if prev_value else 0,
                    'buzz_score': prev_value['buzz_score'] if prev_value else 0
                })

        return historical_data