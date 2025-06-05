import logging
from datetime import datetime, timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)

def update_artist_metrics_if_needed(artist, force_update=False):
    """
    Update artist metrics if they haven't been updated in the last 7 days
    or if force_update is True.
    
    Args:
        artist: Artist instance
        force_update (bool): If True, update metrics regardless of last update time
        
    Returns:
        bool: True if metrics were updated, False otherwise
    """
    if not artist.soundcharts_uuid:
        return False
        
    # Check if we need to update (not updated in last 7 days)
    needs_update = force_update or \
                 not artist.last_metrics_update or \
                 (timezone.now() - artist.last_metrics_update) > timedelta(days=7)
    
    if needs_update:
        try:
            result = artist.update_metrics_from_soundcharts()
            if result.get('success'):
                logger.info(f"Updated metrics for artist {artist.id}")
                return True
            else:
                logger.warning(f"Failed to update metrics for artist {artist.id}: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error updating metrics for artist {artist.id}: {str(e)}")
            
    return False
