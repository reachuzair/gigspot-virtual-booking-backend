from django.utils import timezone
from django.db.models import F
from custom_auth.models import Artist

class BuzzScoreService:
    """
    Service class for calculating and managing artist buzz scores.
    The buzz score is a value between 0-500 that represents an artist's current popularity and momentum.
    
    This service is now primarily used through the Artist model's save method and the update_metrics_from_soundcharts method.
    """
    
    # Weights for different metrics (sum should be 1.0)
    WEIGHTS = {
        'follower_growth': 0.25,      # Growth rate of total followers
        'engagement_rate': 0.25,      # Current engagement rate
        'recent_activity': 0.20,      # Recent releases, posts, etc.
        'playlist_performance': 0.15,  # Playlist adds and streams
        'consistency': 0.15           # Consistency in performance
    }
    
    # Threshold for "On Fire" status (0-500)
    ON_FIRE_THRESHOLD = 350
    
    @classmethod
    def calculate_buzz_score(cls, artist):
        """
        Calculate the buzz score for a single artist.
        
        Args:
            artist: Artist instance to calculate score for
            
        Returns:
            int: Buzz score between 0-500
        """
        if not artist:
            return 0
            
        # Get or calculate each component (0-100 scale)
        components = {
            'follower_growth': cls._calculate_follower_growth_score(artist),
            'engagement_rate': cls._calculate_engagement_score(artist),
            'recent_activity': cls._calculate_recent_activity_score(artist),
            'playlist_performance': cls._calculate_playlist_score(artist),
            'consistency': cls._calculate_consistency_score(artist)
        }
        
        # Calculate weighted sum
        score = sum(components[metric] * weight 
                   for metric, weight in cls.WEIGHTS.items())
        
        # Ensure score is within bounds
        return max(0, min(500, int(round(score))))
    
    @classmethod
    def _calculate_follower_growth_score(cls, artist):
        """Calculate score based on follower growth rate (0-100)"""
        # Get historical follower data (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        
        # In a real implementation, you would query historical data
        # For now, we'll use a simplified version with current data
        total_followers = sum([
            artist.instagram_followers or 0,
            artist.tiktok_followers or 0,
            artist.spotify_followers or 0,
            artist.youtube_subscribers or 0
        ])
        
        # Simplified growth calculation
        # In a real system, you would compare with historical data
        growth_rate = 0.1  # Default growth rate
        
        # Convert growth rate to 0-100 score
        return min(100, max(0, 50 + (growth_rate * 1000)))
    
    @classmethod
    def _calculate_engagement_score(cls, artist):
        """Calculate score based on engagement rate (0-100)"""
        # Engagement rate is already a percentage (0-100)
        engagement = artist.engagement_rate or 0
        
        # Normalize to 0-100 scale (assuming typical engagement rates 0-10%)
        return min(100, engagement * 10)
    
    @classmethod
    def _calculate_recent_activity_score(cls, artist):
        """Calculate score based on recent activity (0-100)"""
        # In a real system, you would check for recent releases, posts, etc.
        # For now, we'll use a simplified version
        
        # Check if artist has been active recently
        if artist.last_metrics_update:
            days_since_update = (timezone.now() - artist.last_metrics_update).days
            if days_since_update <= 7:  # Active in the last week
                return 80
            elif days_since_update <= 30:  # Active in the last month
                return 60
        
        return 30  # Default for no recent activity
    
    @classmethod
    def _calculate_playlist_score(cls, artist):
        """Calculate score based on playlist performance (0-100)"""
        # Normalize playlist views to a 0-100 score
        views = artist.playlist_views or 0
        
        # Logarithmic scale to handle large ranges
        if views <= 0:
            return 0
            
        # Log scale: log10(views + 1) * 20, capped at 100
        return min(100, math.log10(views + 1) * 20)
    
    @classmethod
    def _calculate_consistency_score(cls, artist):
        """Calculate score based on consistency of performance (0-100)"""
        # In a real system, you would analyze historical data
        # For now, we'll return a default value
        return 70
    
    @classmethod
    def update_artist_buzz_score(cls, artist, save=True):
        """
        Update the buzz score for an artist.
        
        Args:
            artist: Artist instance to update
            save: Whether to save the artist after updating
            
        Returns:
            tuple: (new_score, is_on_fire)
        """
        if not artist:
            return 0, False
            
        # Calculate new score
        new_score = cls.calculate_buzz_score(artist)
        is_on_fire = new_score >= cls.ON_FIRE_THRESHOLD
        
        # Update artist
        artist.buzz_score = new_score
        artist.onFireStatus = is_on_fire
        
        if save:
            artist.save(update_fields=['buzz_score', 'onFireStatus'])
            
        return new_score, is_on_fire
    
    @classmethod
    def update_all_artists_buzz_scores(cls, batch_size=100):
        """
        Update buzz scores for all artists in batches.
        
        Args:
            batch_size: Number of artists to process in each batch
            
        Returns:
            dict: Results with counts of updated artists and errors
        """
        results = {
            'total_artists': 0,
            'updated': 0,
            'errors': 0,
            'now_on_fire': 0,
            'no_longer_on_fire': 0
        }
        
        # Get all artists
        queryset = Artist.objects.all()
        results['total_artists'] = queryset.count()
        
        # Process in batches
        for i in range(0, results['total_artists'], batch_size):
            batch = queryset[i:i + batch_size]
            for artist in batch:
                try:
                    # Get previous onFireStatus
                    was_on_fire = artist.onFireStatus
                    
                    # Update score
                    new_score, is_on_fire = cls.update_artist_buzz_score(artist, save=True)
                    
                    # Update counters
                    results['updated'] += 1
                    
                    # Track changes in onFireStatus
                    if is_on_fire and not was_on_fire:
                        results['now_on_fire'] += 1
                    elif was_on_fire and not is_on_fire:
                        results['no_longer_on_fire'] += 1
                        
                except Exception as e:
                    results['errors'] += 1
                    # Log the error
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error updating buzz score for artist {artist.id}: {str(e)}")
        
        return results
