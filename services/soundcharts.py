import os
import requests
import logging
from django.conf import settings
from urllib.parse import quote
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SoundChartsAPI:
    BASE_URL = "https://customer.api.soundcharts.com/api/v2"
    
    def __init__(self):
        self.app_id = os.getenv('SOUNDSCHART_APP_ID')
        self.api_key = os.getenv('SOUNDSCHART_API_KEY')
        
        if not self.app_id or not self.api_key:
            raise ValueError("SoundCharts credentials not configured")
    
    def _make_request(self, endpoint, params=None):
        """Helper method to make authenticated requests"""
        headers = {
            'x-app-id': self.app_id,
            'x-api-key': self.api_key
        }
        
        try:
            response = requests.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"HTTP error occurred: {http_err}")
            return {'error': str(http_err), 'status_code': response.status_code}
        except Exception as err:
            logger.error(f"Error making request to SoundCharts: {err}")
            return {'error': str(err)}
    
    def search_artist_by_name(self, artist_name, limit=10, offset=0):
        """Search for an artist by name"""
        endpoint = f"{self.BASE_URL}/artist/search/{quote(artist_name)}"
        params = {'offset': offset, 'limit': limit}
        return self._make_request(endpoint, params)
    
    def get_artist_metrics(self, soundcharts_uuid):
        """Get detailed metrics for an artist including followers and streams"""
        # Get artist summary for followers
        summary_endpoint = f"{self.BASE_URL}/artist/{soundcharts_uuid}/summary"
        summary = self._make_request(summary_endpoint)
        
        if 'error' in summary:
            return summary
        
        # Get streaming metrics (last 30 days)
        end_date = datetime.utcnow().strftime('%Y-%m-%d')
        start_date = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        streams_endpoint = f"{self.BASE_URL}/artist/{soundcharts_uuid}/streaming/spotify"
        streams_params = {
            'start': start_date,
            'end': end_date,
            'aggregateBy': 'month'
        }
        streams_data = self._make_request(streams_endpoint, streams_params)
        
        if 'error' in streams_data:
            return streams_data
        
        # Calculate total streams
        total_streams = sum(item.get('streams', 0) for item in streams_data.get('items', []))
        
        return {
            'follower_count': summary.get('followerCount', 0),
            'monthly_listeners': summary.get('monthlyListeners', 0),
            'total_streams': total_streams,
            'last_updated': datetime.utcnow().isoformat()
        }
    
    def update_artist_tier(self, artist):
        """Update artist's tier based on their metrics"""
        if not artist.soundcharts_uuid:
            return {'error': 'No SoundCharts UUID found for artist'}
        
        metrics = self.get_artist_metrics(artist.soundcharts_uuid)
        
        if 'error' in metrics:
            return metrics
        
        # Get the appropriate tier based on follower count
        from custom_auth.models import PerformanceTier
        new_tier = PerformanceTier.get_tier_for_followers(metrics['follower_count'])
        
        # Update artist metrics and tier
        artist.followers = metrics['follower_count']
        artist.monthly_listeners = metrics['monthly_listeners']
        artist.total_streams = metrics['total_streams']
        artist.performance_tier = new_tier
        artist.save()
        
        return {
            'success': True,
            'tier': new_tier,
            'follower_count': metrics['follower_count'],
            'monthly_listeners': metrics['monthly_listeners'],
            'total_streams': metrics['total_streams']
        }