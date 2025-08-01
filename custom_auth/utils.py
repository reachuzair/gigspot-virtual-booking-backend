import logging
from datetime import timedelta
from django.utils import timezone
from artists.tasks import update_artist_metrics
from utils.tasks import run_async

logger = logging.getLogger(__name__)

def update_artist_metrics_if_needed(artist, force_update=False):
    """
    Update an artist's metrics if they haven't been updated recently.
    
    Args:
        artist: The Artist instance to update
        force_update (bool): If True, force update even if recently updated
        
    Returns:
        bool: True if metrics were updated or scheduled for update, False otherwise
    """
    if not artist or not hasattr(artist, 'soundcharts_uuid') or not artist.soundcharts_uuid:
        logger.debug(f"Skipping metrics update for artist {getattr(artist, 'id', 'unknown')}: No SoundCharts UUID")
        return False
    
    # Check if we should update (if forced or last update was more than 24 hours ago)
    should_update = force_update
    
    if not should_update and hasattr(artist, 'last_metrics_update'):
        update_threshold = timezone.now() - timedelta(hours=24)
        should_update = artist.last_metrics_update is None or artist.last_metrics_update < update_threshold
    
    if not should_update:
        logger.debug(f"Skipping metrics update for artist {artist.id} - recently updated")
        return False
    
    try:
        # Run the update in a background task
        run_async(update_artist_metrics, artist_id=artist.id)
        logger.info(f"Scheduled metrics update for artist {artist.id}")
        return True
    except Exception as e:
        logger.error(f"Error scheduling metrics update for artist {getattr(artist, 'id', 'unknown')}: {str(e)}")
        return False
