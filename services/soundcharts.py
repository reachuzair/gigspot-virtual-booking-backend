import os
import requests
from django.conf import settings
from urllib.parse import quote

class SoundsChartAPI:
    BASE_URL = "https://customer.api.soundcharts.com/api/v2"  # Updated for v2.0
    
    def __init__(self):
        self.app_id = os.getenv('SOUNDSCHART_APP_ID')
        self.api_key = os.getenv('SOUNDSCHART_API_KEY')
        
        if not self.app_id or not self.api_key:
            raise ValueError("SoundsChart credentials not configured")
    
    def search_artist_by_name(self, artist_name, limit=10, offset=0):
        """Search for an artist by name using v2.0 API"""
        endpoint = f"{self.BASE_URL}/artist/search/{artist_name}"
        
        headers = {
            'X-APP-ID': self.app_id,
            'X-API-KEY': self.api_key,
            'Accept': 'application/json'
        }
        
        params = {
            'limit': limit,
            'offset': offset
            # Add other parameters as needed
        }
        
        try:
            response = requests.get(endpoint, headers=headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
            return {'detail': str(http_err), 'status_code': response.status_code}
        except Exception as err:
            print(f"Other error occurred: {err}")
            return {'detail': str(err)}