import os
import requests
import logging

logger = logging.getLogger(__name__)

class SoundChartsAPI:
    """
    Client for interacting with the SoundCharts API.
    
    This client is streamlined to only include the functionality required for
    calculating artist buzz scores. It handles authentication and provides methods
    to fetch artist details, stats, social followers, and audience data.
    """
    
    BASE_URL = "https://customer.api.soundcharts.com"
    ENDPOINTS = {
        'artist': '/api/v2.9/artist/{uuid}',
        'artist_stats': '/api/v2/artist/{uuid}/current/stats',
        'artist_audience': '/api/v2/artist/{uuid}/audience/{platform}',
        'artist_social_followers': '/api/v2.37/artist/{uuid}/social/{platform}/followers/'
    }

    def __init__(self):
        """Initialize the SoundCharts API client with credentials from environment variables."""
        from django.conf import settings
        self.app_id = os.getenv('SOUNDCHART_APP_ID') or getattr(settings, 'SOUNDCHART_APP_ID', None)
        self.api_key = os.getenv('SOUNDCHART_API_KEY') or getattr(settings, 'SOUNDCHART_API_KEY', None)

        if not self.app_id or not self.api_key:
            logger.error("SoundCharts API credentials (SOUNDCHART_APP_ID, SOUNDCHART_API_KEY) are not set.")
            raise ValueError("Missing SoundCharts API credentials.")

        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'x-app-id': str(self.app_id),
            'x-api-key': str(self.api_key)
        })
        
        # Add search endpoint
        self.ENDPOINTS['search_artists'] = '/api/v2/search/artists'
        
    def search_artist_by_name(self, name):
        """
        Search for an artist by name.
        
        Args:
            name (str): Artist name to search for
            
        Returns:
            dict: Search results or error information
        """
        if not name:
            return {'detail': 'Artist name is required', 'status_code': 400}
            
        params = {
            'q': name,
            'limit': 1  # Get top match only
        }
        
        status, data, error = self._make_request(
            'search_artists',
            params=params
        )
        
        if status == 200 and isinstance(data, dict) and 'items' in data and data['items']:
            # Return the first match
            artist = data['items'][0]
            return {
                'uuid': artist.get('uuid'),
                'name': artist.get('name'),
                'image_url': artist.get('imageUrl'),
                'platforms': artist.get('platforms', {})
            }
        elif status == 200:
            return {'detail': 'No artists found', 'status_code': 404}
        else:
            return {
                'detail': error or data.get('detail', 'Unknown error'),
                'status_code': status
            }

    def _make_request(self, endpoint_name, params=None, **path_params):
        """
        Make an HTTP GET request to the SoundCharts API.
        
        Args:
            endpoint_name (str): The name of the endpoint from ENDPOINTS.
            params (dict, optional): Query parameters for the request.
            **path_params: Parameters to format into the endpoint URL (e.g., uuid, platform).
        
        Returns:
            tuple: (status_code, response_data, error_message)
        """
        if not self.app_id or not self.api_key:
            error_msg = "Missing SoundCharts API credentials (app_id or api_key)"
            logger.error(error_msg)
            return 401, {'detail': error_msg}, error_msg
            
        try:
            # Build the URL
            endpoint = self.ENDPOINTS.get(endpoint_name)
            if not endpoint:
                error_msg = f"Unknown endpoint: {endpoint_name}"
                logger.error(error_msg)
                return 404, {'detail': error_msg}, error_msg
                
            url = self.BASE_URL + endpoint.format(**path_params)
            
            logger.debug(f"Making request to {url} with params: {params}")
            
            # Make the request
            response = self.session.get(
                url,
                params=params,
                timeout=30  # 30 second timeout
            )
            
            # Log rate limit info
            if 'X-RateLimit-Remaining' in response.headers:
                remaining = response.headers['X-RateLimit-Remaining']
                reset = response.headers.get('X-RateLimit-Reset', 'N/A')
                logger.debug(f"Rate limit - Remaining: {remaining}, Reset: {reset}")
            
            # Check for error responses
            response.raise_for_status()
            
            # Parse JSON response
            try:
                data = response.json()
                logger.debug(f"API response: {data}")
                return response.status_code, data, None
            except ValueError as e:
                error_msg = f"Failed to parse JSON response: {str(e)}"
                logger.error(f"{error_msg}. Response: {response.text[:500]}")
                return 500, {'detail': error_msg}, error_msg
                
        except requests.exceptions.RequestException as e:
            status_code = getattr(e.response, 'status_code', 500) if hasattr(e, 'response') else 500
            error_msg = str(e)
            
            # Try to get more detailed error info if available
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('detail', error_msg)
                except:
                    error_msg = e.response.text or error_msg
            
            logger.error(f"API request failed: {error_msg}")
            return status_code, {'detail': error_msg}, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return 500, {'detail': error_msg}, error_msg
            # Log rate limit headers if present
            if 'X-RateLimit-Remaining' in response.headers:
                logger.info(f"[DEBUG] Rate limit - Remaining: {response.headers['X-RateLimit-Remaining']} | Limit: {response.headers.get('X-RateLimit-Limit', '?')}")
            
            response.raise_for_status()
            
            # Parse JSON response
            json_data = response.json()
            logger.info(f"[DEBUG] Parsed JSON response: {json_data}")
            
            return response.status_code, json_data, None
            
        except requests.exceptions.RequestException as e:
            status_code = e.response.status_code if e.response is not None else 500
            error_msg = str(e)
            logger.error(f"API request to {url} failed with status {status_code}: {error_msg}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Error response content: {e.response.text}")
            return status_code, {'detail': error_msg}, error_msg

    def get_artist_details(self, artist_uuid):
        """
        Get detailed information about an artist by their UUID.
        
        Args:
            artist_uuid (str): The SoundCharts artist UUID
            
        Returns:
            dict: Artist details or error information
        """
        if not artist_uuid:
            return {'detail': 'Artist UUID is required', 'status_code': 400}
            
        status, data, error = self._make_request('artist', uuid=artist_uuid)
        
        if status == 200 and isinstance(data, dict):
            return data
        else:
            return {
                'detail': error or data.get('detail', 'Unknown error'),
                'status_code': status
            }

    def get_artist_stats(self, artist_uuid):
        """
        Get current statistics for an artist.
        
        Args:
            artist_uuid (str): The SoundCharts artist UUID
            
        Returns:
            dict: Artist statistics or error information
        """
        if not artist_uuid:
            return {'detail': 'Artist UUID is required', 'status_code': 400}
            
        status, data, error = self._make_request(
            'artist_stats', 
            uuid=artist_uuid, 
            params={'period': '7'}
        )
        
        if status == 200 and isinstance(data, dict):
            return data
        else:
            return {
                'detail': error or data.get('detail', 'Unknown error'),
                'status_code': status
            }

    def get_artist_social_followers(self, artist_uuid, platform):
        """
        Get social media followers for an artist on a specific platform.
        
        Args:
            artist_uuid (str): The SoundCharts artist UUID
            platform (str): Social platform (e.g., 'instagram', 'spotify')
            
        Returns:
            dict: Follower data including count and growth rate
        """
        if not artist_uuid or not platform:
            return {
                'success': False,
                'detail': 'Artist UUID and platform are required',
                'status_code': 400
            }
        
        # First, get the artist stats which contains the social data
        status, stats_data, error = self._make_request('artist_stats', uuid=artist_uuid, params={'period': '7'})
        if status != 200 or not isinstance(stats_data, dict) or 'social' not in stats_data:
            return {
                'success': False,
                'detail': error or 'Failed to get artist stats',
                'status_code': status if status != 200 else 500
            }
        
        # Initialize response
        followers_data = {
            'success': True,
            'count': 0,
            'growth_rate': 0,
            'platform': platform,
            'last_updated': None
        }
        
        try:
            # Find the platform in the social data
            platform_data = next(
                (item for item in stats_data['social'] 
                 if item.get('platform') == platform),
                None
            )
            
            if platform_data:
                followers_data['count'] = int(platform_data.get('value', 0))
                
                # Calculate growth rate if available
                if 'evolution' in platform_data and 'percentEvolution' in platform_data:
                    followers_data['growth_rate'] = round(float(platform_data['percentEvolution']), 2)
                
                # Add last updated date if available
                if 'date' in platform_data:
                    followers_data['last_updated'] = platform_data['date']
            
            logger.info(f"[DEBUG] {platform} followers: {followers_data['count']}, "
                       f"growth: {followers_data['growth_rate']}%")
                        
        except (TypeError, ValueError, AttributeError, KeyError) as e:
            error_msg = f"Error processing {platform} data: {str(e)}"
            logger.error(error_msg, exc_info=True)
            followers_data.update({
                'success': False,
                'detail': error_msg
            })
        
        return followers_data

    def get_artist_audience(self, artist_uuid, platform='instagram'):
        """
        Get audience data for an artist on a specific platform.
        
        Args:
            artist_uuid (str): The SoundCharts artist UUID
            platform (str, optional): Social platform (e.g., 'instagram', 'spotify', 'tiktok', 'youtube'). 
                                   Defaults to 'instagram'.
            
        Returns:
            dict: A dictionary containing:
                - success (bool): Whether the operation was successful
                - {platform}_followers (int): Number of followers for the platform
                - error (str, optional): Error message if success is False
                - status_code (int, optional): HTTP status code
        """
        # Make the API request
        status, data, error = self._make_request('artist_audience', uuid=artist_uuid, platform=platform)
        
        if status != 200:
            return {
                'success': False,
                'detail': data.get('detail', error or 'Unknown error'),
                'status_code': status
            }
        
        try:
            # Check if we have valid data
            if not isinstance(data, dict) or 'items' not in data or not data['items']:
                return {
                    'success': False,
                    'detail': 'No audience data available',
                    'status_code': 404
                }
            
            # Get the most recent data point (first item in the items array)
            latest_data = data['items'][0]
            follower_count = latest_data.get('followerCount', 0)
            
            # Return the platform-specific follower count field name that matches our model
            return {
                'success': True,
                f'{platform}_followers': follower_count,
                'status_code': status
            }
            
        except (KeyError, IndexError, AttributeError) as e:
            logger.error(f"Error processing audience data: {str(e)}", exc_info=True)
            return {
                'success': False,
                'detail': f'Error processing audience data: {str(e)}',
                'status_code': 500
            }

    def parse_artist_metrics(self, response_data):
        """
        Parse the artist metrics from the SoundCharts states endpoint response.
        Returns a dictionary with only the fields needed for buzz score calculation.
        
        Args:
            response_data (dict): Raw response from the states endpoint
            
        Returns:
            dict: Parsed metrics with artist info and metrics
        """
        if not response_data or not isinstance(response_data, dict):
            return {'detail': 'Invalid response data', 'success': False}
            
        try:
            # Extract basic artist info from related section
            related = response_data.get('related', {})
            artist_info = {
                'id': related.get('uuid'),
                'name': related.get('name'),
                'platforms': {},
                'image_url': related.get('imageUrl'),
                'app_url': related.get('appUrl')
            }
            
            # Initialize metrics dictionary with default values
            metrics = {
                # Social metrics (will be populated from social array)
                'instagram_followers': 0,
                'tiktok_followers': 0,
                'youtube_subscribers': 0,
                'spotify_followers': 0,
                'follower_count': 0,  # Will be sum of all platform followers
                
                # Engagement
                'engagement_rate': 0.0,
                
                # Streaming metrics (will be populated from streaming array)
                'monthly_listeners': 0,
                'streams': 0,
                
                # Scores (from score array)
                'buzz_score': 0,
                'fanbase_score': 0,
                'trending_score': 0,
                'onFireStatus': False
            }
            
            # Process social metrics
            social_metrics = response_data.get('social', [])
            for platform_data in social_metrics:
                platform = platform_data.get('platform')
                followers = platform_data.get('value', 0)
                
                if platform == 'instagram':
                    metrics['instagram_followers'] = followers
                elif platform == 'tiktok':
                    metrics['tiktok_followers'] = followers
                elif platform == 'youtube':
                    metrics['youtube_subscribers'] = followers
                elif platform == 'spotify':
                    metrics['spotify_followers'] = followers
            
            # Calculate total follower count
            metrics['follower_count'] = sum(
                metrics[f'{p}_followers'] 
                for p in ['instagram', 'tiktok', 'youtube', 'spotify']
            )
            
            # Process streaming metrics
            streaming_metrics = response_data.get('streaming', [])
            for stream_data in streaming_metrics:
                platform = stream_data.get('platform')
                value = stream_data.get('value', 0)
                
                if platform == 'spotify':
                    metrics['monthly_listeners'] = value
                # Add more platforms as needed
                
                # Sum up streams across all platforms
                metrics['streams'] += value
            
            # Process scores
            score_metrics = response_data.get('score', [])
            for score_data in score_metrics:
                score_type = score_data.get('type')
                value = score_data.get('value', 0)
                
                if score_type == 'sc_score':
                    metrics['buzz_score'] = value
                elif score_type == 'sc_fanbase':
                    metrics['fanbase_score'] = value
                elif score_type == 'sc_trending':
                    metrics['trending_score'] = value
            
            # Calculate platform consistency (number of platforms with followers)
            metrics['platform_consistency'] = sum(
                1 for p in ['instagram', 'tiktok', 'youtube', 'spotify']
                if metrics[f'{p}_followers'] > 0
            )
            
            return {
                'success': True,
                'artist': artist_info,
                'metrics': metrics
            }
            
        except Exception as e:
            logger.error(f"Error parsing artist metrics: {str(e)}")
            return {
                'success': False,
                'detail': str(e)
            }

    def get_artist_buzz_score(self, artist_uuid):
        """
        Calculate the buzz score and analytics for an artist.
        Always returns a dictionary with at least a 'success' key.
        
        Args:
            artist_uuid (str): The SoundCharts UUID of the artist
            
        Returns:
            dict: A dictionary containing:
                - success (bool): Whether the operation was successful
                - error (str, optional): Error message if success is False
                - buzz_score (float): The calculated buzz score (0-100)
                - metrics (dict): Detailed metrics used in the calculation
        """
        # Initialize default response
        default_response = {
            'success': False,
            'detail': 'Unknown error',
            'buzz_score': 0,
            'metrics': {}
        }
        
        def handle_error(error_msg, exc=None):
            """Helper function to log errors and return error response"""
            if exc:
                logger.exception(f"{error_msg}: {str(exc)}")
            else:
                logger.error(error_msg)
            return {**default_response, 'detail': error_msg}
            
        try:
            # Input validation
            if not artist_uuid:
                return handle_error("No artist UUID provided")
                
            logger.info(f"[DEBUG] Getting buzz score for artist: {artist_uuid}")
            
            # Get artist details
            try:
                print("[DEBUG] Fetching artist details...")
                artist_details = self.get_artist_details(artist_uuid)
                print(f"[DEBUG] Artist details: {artist_details}")
                if not artist_details or 'detail' in artist_details: 
                    error_msg = f"Failed to get artist details: {artist_details.get('detail', 'Unknown error')}" if artist_details else "No artist details returned"
                    return handle_error(error_msg)
            except Exception as e:
                return handle_error("Error getting artist details", e)

            # Get artist stats
            try:
                print("[DEBUG] Fetching artist stats...")
                artist_stats = self.get_artist_stats(artist_uuid)
                print(f"[DEBUG] Artist stats: {artist_stats}")
                if not artist_stats or 'detail' in artist_stats: 
                    error_msg = f"Failed to get artist stats: {artist_stats.get('detail', 'Unknown error')}" if artist_stats else "No artist stats returned"
                    return handle_error(error_msg)
            except Exception as e:
                return handle_error("Error getting artist stats", e)
                
            # Process social media data
            platforms = ['instagram', 'tiktok', 'youtube', 'spotify']
            social_data = {}
            
            for platform in platforms:
                try:
                    if platform == 'spotify':
                        # For Spotify, get data from artist details
                        spotify_data = {
                            'followers': artist_details.get('follower_count', 0),
                            'growth_rate': 0,  # Default growth rate for Spotify
                            'monthly_listeners': artist_details.get('monthly_listeners', 0)
                        }
                        print(f"[DEBUG] Spotify data: {spotify_data}")
                        social_data[platform] = spotify_data
                    else:
                        # For other platforms, use social followers endpoint
                        print(f"[DEBUG] Getting {platform} followers for artist {artist_uuid}...")
                        followers = self.get_artist_social_followers(artist_uuid, platform)
                        print(f"[DEBUG] {platform} followers response: {followers}")
                        
                        if followers and isinstance(followers, dict):
                            social_data[platform] = {
                                'followers': followers.get('count', 0),
                                'growth_rate': followers.get('growth_rate', 0),
                                'monthly_listeners': None  # Not available for all platforms
                            }
                        else:
                            social_data[platform] = {'followers': 0, 'growth_rate': 0, 'monthly_listeners': None}
                except Exception as e:
                    error_msg = f"Error getting {platform} followers: {str(e)}"
                    print(f"[ERROR] {error_msg}")
                    social_data[platform] = {'followers': 0, 'growth_rate': 0, 'monthly_listeners': None}
            
            # Calculate metrics
            try:
                print("[DEBUG] Calculating buzz score metrics...")
                result = self._calculate_buzz_score_metrics(artist_details, artist_stats, social_data)
                print(f"[DEBUG] Final buzz score result: {result}")
                return result
            except Exception as e:
                return handle_error("Error calculating buzz score metrics", e)
                
        except Exception as e:
            return handle_error("Unexpected error in get_artist_buzz_score", e)

    def _calculate_buzz_score_metrics(self, artist_details, artist_stats, social_data):
        """
        Calculate the buzz score and metrics from the collected data.
        
        Args:
            artist_details (dict): Artist details from SoundCharts API
            artist_stats (dict): Artist stats from SoundCharts API
            social_data (dict): Social media data for the artist
            
        Returns:
            dict: A dictionary containing the buzz score and metrics
        """
        # Log the collected social data
        logger.info(f"[DEBUG] Social data collected: {social_data}")
        
        # Calculate total followers and growth
        total_followers = sum(data.get('followers', 0) for data in social_data.values())
        total_growth = sum(data.get('growth_rate', 0) for data in social_data.values())
        logger.info(f"[DEBUG] Calculated totals - Followers: {total_followers}, Growth: {total_growth}")

        # Get engagement data
        logger.info("[DEBUG] Fetching Instagram audience data...")
        audience_data = self.get_artist_audience(artist_details.get('id'), 'instagram')
        logger.info(f"[DEBUG] Raw audience data: {audience_data}")
        
        engagement_rate = audience_data.get('audience', {}).get('engagement_rate', 0) if audience_data.get('success') else 0
        logger.info(f"[DEBUG] Extracted engagement rate: {engagement_rate}")

        # Get and validate popularity
        popularity = artist_stats.get('popularity', 0)
        logger.info(f"[DEBUG] Raw popularity from stats: {popularity} (type: {type(popularity)})")
        
        try:
            popularity = float(popularity) if popularity is not None else 0
            logger.info(f"[DEBUG] Converted popularity to float: {popularity}")
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to convert popularity '{popularity}' to float: {e}")
            popularity = 0

        # Calculate buzz score components with detailed logging
        follower_component = (total_followers * 0.3) / 1000000
        growth_component = (total_growth * 0.3) * 100
        engagement_component = (engagement_rate * 0.2) * 100
        popularity_component = (popularity * 0.2)
        
        logger.info(
            "[DEBUG] Buzz score components - "
            f"Followers: {follower_component:.6f} (from {total_followers} * 0.3 / 1M), "
            f"Growth: {growth_component:.6f} (from {total_growth} * 0.3 * 100), "
            f"Engagement: {engagement_component:.6f} (from {engagement_rate} * 0.2 * 100), "
            f"Popularity: {popularity_component:.6f} (from {popularity} * 0.2)"
        )

        buzz_score = follower_component + growth_component + engagement_component + popularity_component
        buzz_score = min(100, max(0, buzz_score))
        logger.info(f"[DEBUG] Final buzz score: {buzz_score:.2f} (before rounding: {buzz_score})")

        # Prepare platform breakdown with logging
        platform_breakdown = {}
        for platform, data in social_data.items():
            platform_breakdown[platform] = {
                'followers': data.get('followers', 0),
                'growth_rate': data.get('growth_rate'),
                'monthly_listeners': data.get('monthly_listeners')
            }
            logger.info(f"[DEBUG] Platform {platform} breakdown: {platform_breakdown[platform]}")

        # Return the complete result
        return {
            'success': True,
            'buzz_score': round(buzz_score, 1),
            'metrics': {
                'total_followers': int(total_followers),
                'total_growth_rate': round(total_growth, 2),
                'engagement_rate': round(engagement_rate, 2),
                'popularity': popularity,
                'platform_breakdown': platform_breakdown
            }
        }