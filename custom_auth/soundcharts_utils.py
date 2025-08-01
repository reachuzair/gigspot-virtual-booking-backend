import logging
from datetime import datetime, timedelta
from django.utils import timezone
from services.soundcharts import SoundChartsAPI
from .models import PerformanceTier, Artist

logger = logging.getLogger(__name__)

def update_artist_metrics_from_soundcharts(artist, force_update=False):
    """
    Update an artist's metrics and tier from SoundCharts API.

    Args:
        artist (Artist): The artist to update
        force_update (bool): If True, force update even if recently updated

    Returns:
        dict: Result of the update with status and data
    """
    if not artist.soundcharts_uuid:
        return {
            'success': False,
            'detail': 'No SoundCharts UUID set for this artist',
            'code': 'missing_uuid'
        }

    # Skip update if recent (within 24 hours)
    if not force_update and artist.last_tier_update:
        hours_since_update = (timezone.now() - artist.last_tier_update).total_seconds() / 3600
        if hours_since_update < 24:
            return {
                'success': True,
                'cached': True,
                'message': 'Metrics updated recently',
                'tier': artist.performance_tier,
                'tier_display': artist.get_performance_tier_display(),
                'last_updated': artist.last_tier_update.isoformat()
            }

    try:
        soundcharts = SoundChartsAPI()
        artist_details = soundcharts.get_artist_details(artist.soundcharts_uuid)

        if not artist_details:
            return {
                'success': False,
                'detail': 'Failed to fetch artist details from SoundCharts',
                'code': 'fetch_error'
            }

        follower_count = artist_details.get('followerCount', 0)
        monthly_listeners = artist_details.get('monthlyListeners', 0)

        total_stream_count = 0
        platforms = artist_details.get('platforms', {})

        instagram_count = tiktok_count = spotify_count = youtube_count = 0

        for name, data in platforms.items():
            if isinstance(data, dict):
                total_stream_count += data.get('streams', {}).get('total', 0) or 0

                if name.lower() == 'instagram':
                    instagram_count = data.get('followers', 0)
                elif name.lower() == 'tiktok':
                    tiktok_count = data.get('followers', 0)
                elif name.lower() == 'spotify':
                    spotify_count = data.get('followers', 0)
                elif name.lower() == 'youtube':
                    youtube_count = data.get('followers', 0)

        new_tier = PerformanceTier.get_tier_by_metrics(
            follower_count=follower_count,
            monthly_listeners=monthly_listeners,
            total_streams=total_stream_count
        )

        update_fields = []

        if artist.instagram_followers != instagram_count:
            artist.instagram_followers = instagram_count
            update_fields.append('instagram_followers')
        if artist.tiktok_followers != tiktok_count:
            artist.tiktok_followers = tiktok_count
            update_fields.append('tiktok_followers')
        if artist.spotify_followers != spotify_count:
            artist.spotify_followers = spotify_count
            update_fields.append('spotify_followers')
        if artist.youtube_subscribers != youtube_count:
            artist.youtube_subscribers = youtube_count
            update_fields.append('youtube_subscribers')

        if hasattr(artist, 'monthly_listeners') and artist.monthly_listeners != monthly_listeners:
            artist.monthly_listeners = monthly_listeners
            update_fields.append('monthly_listeners')

        if hasattr(artist, 'total_streams') and artist.total_streams != total_stream_count:
            artist.total_streams = total_stream_count
            update_fields.append('total_streams')

        if artist.performance_tier != new_tier:
            artist.performance_tier = new_tier
            update_fields.append('performance_tier')

        artist.last_tier_update = timezone.now()
        update_fields.append('last_tier_update')

        if update_fields:
            artist.save(update_fields=update_fields)

        return {
            'success': True,
            'tier': new_tier,
            'tier_display': artist.get_performance_tier_display(),
            'monthly_listeners': monthly_listeners,
            'total_streams': total_stream_count,
            'last_updated': artist.last_tier_update.isoformat(),
            'platform_followers': {
                'instagram': instagram_count,
                'tiktok': tiktok_count,
                'spotify': spotify_count,
                'youtube': youtube_count
            }
        }

    except Exception as e:
        logger.error(f"Error updating artist metrics from SoundCharts: {e}", exc_info=True)
        return {
            'success': False,
            'detail': str(e),
            'code': 'update_error'
        }


def update_artist_soundcharts_uuid(artist, soundcharts_uuid, force_update=True):
    """
    Update an artist's SoundCharts UUID and optionally update their metrics.
    
    Args:
        artist (Artist): The artist to update
        soundcharts_uuid (str): The SoundCharts UUID to set
        force_update (bool): If True, update metrics immediately after setting UUID
        
    Returns:
        dict: Result of the operation
    """
    if not soundcharts_uuid:
        return {
            'success': False,
            'detail': 'SoundCharts UUID is required',
            'code': 'missing_uuid'
        }
    
    # Update the UUID
    artist.soundcharts_uuid = soundcharts_uuid
    artist.save(update_fields=['soundcharts_uuid'])
    
    # Update metrics if requested
    if force_update:
        return update_artist_metrics_from_soundcharts(artist, force_update=True)
    
    return {
        'success': True,
        'message': 'SoundCharts UUID updated successfully',
        'soundcharts_uuid': soundcharts_uuid
    }
