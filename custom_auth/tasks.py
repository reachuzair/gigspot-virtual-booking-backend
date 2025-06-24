import logging
from celery import shared_task
from django.utils import timezone
from django.db.models import Q, F
from .models import Artist
from .soundcharts_utils import update_artist_metrics_from_soundcharts

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def update_artist_metrics_task(self, artist_id=None, force_update=False):
    """
    Celery task to update metrics for a single artist or all artists.
    
    Args:
        artist_id (int, optional): ID of the artist to update. If None, updates all artists.
        force_update (bool): If True, force update even if metrics were recently updated.
    """
    try:
        if artist_id:
            # Update a single artist
            try:
                artist = Artist.objects.get(id=artist_id)
                if not artist.soundcharts_uuid:
                    logger.warning(f"Artist {artist_id} has no SoundCharts UUID, skipping")
                    return {"status": "skipped", "reason": "no_soundcharts_uuid"}
                
                result = update_artist_metrics_from_soundcharts(artist, force_update=force_update)
                if result.get('success'):
                    if result.get('cached'):
                        return {"status": "cached", "artist_id": artist_id}
                    return {"status": "updated", "artist_id": artist_id, "tier": result.get('tier')}
                else:
                    logger.error(f"Failed to update metrics for artist {artist_id}: {result.get('error')}")
                    return {"status": "error", "artist_id": artist_id, "error": result.get('error')}
                    
            except Artist.DoesNotExist:
                logger.error(f"Artist with ID {artist_id} not found")
                return {"status": "error", "error": f"Artist {artist_id} not found"}
                
        else:
            # Batch update all artists with SoundCharts UUID, ordered by last update time (oldest first)
            # and prioritizing artists with more followers
            artists = Artist.objects.exclude(
                Q(soundcharts_uuid__isnull=True) | Q(soundcharts_uuid__exact='')
            ).order_by('last_tier_update', '-follower_count')
            
            updated = 0
            skipped = 0
            errors = 0
            
            for artist in artists.iterator():
                try:
                    result = update_artist_metrics_from_soundcharts(artist, force_update=force_update)
                    if result.get('success'):
                        if not result.get('cached'):
                            updated += 1
                        else:
                            skipped += 1
                    else:
                        errors += 1
                        logger.warning(f"Failed to update metrics for artist {artist.id}: {result.get('error')}")
                except Exception as e:
                    errors += 1
                    logger.error(f"Error updating metrics for artist {artist.id}: {str(e)}", exc_info=True)
            
            return {
                "status": "batch_complete",
                "total_artists": artists.count(),
                "updated": updated,
                "skipped": skipped,
                "errors": errors
            }
            
    except Exception as e:
        logger.error(f"Error in update_artist_metrics_task: {str(e)}", exc_info=True)
        # Retry the task with exponential backoff
        raise self.retry(exc=e, countdown=60 * 5)  # Retry after 5 minutes


def schedule_daily_artist_metrics_update():
    """
    Schedule a daily task to update metrics for all artists.
    This should be called from a Celery beat schedule.
    """
    from datetime import datetime, time
    from celery.schedules import crontab
    
    # Schedule the task to run daily at 3 AM
    return {
        'update_artist_metrics_daily': {
            'task': 'custom_auth.tasks.update_artist_metrics_task',
            'schedule': crontab(hour=3, minute=0),  # 3 AM daily
            'args': (None, False),  # Update all artists, don't force update
            'options': {
                'expires': 60 * 60 * 23,  # Expire after 23 hours
            },
        },
    }
