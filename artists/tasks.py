import logging
from django.utils import timezone
from datetime import timedelta, datetime, date
from django.db.models import Q, F, Max, Min
from custom_auth.models import Artist
from django.db import transaction, models
from utils.tasks import run_async
from django.db.models.functions import Coalesce

# Sentry is optional
try:
    from sentry_sdk import capture_exception
except ImportError:
    def capture_exception(error, **kwargs):
        logger.error(f"Sentry not available. Error: {str(error)}")
        return None

logger = logging.getLogger(__name__)

# Maximum number of retries for failed updates
MAX_RETRIES = 3
# Time to wait between retries (in seconds)
RETRY_DELAY = 300  # 5 minutes
# Batch size for processing artists
BATCH_SIZE = 50
# Minimum time between updates for the same artist (in hours)
MIN_UPDATE_INTERVAL = 6

def update_daily_metrics():
    """
    Update metrics for all artists and check for 'on fire' status based on buzz score changes.
    This should be run once per day.
    
    Returns:
        dict: Summary of the update operation with counts and status
    """
    try:
        updated = 0
        on_fire_count = 0
        
        # Get all artists with their current metrics
        artists = Artist.objects.all()
        
        for artist in artists.iterator(chunk_size=BATCH_SIZE):
            try:
                # Get the metrics summary which will update onFireStatus
                metrics_summary = artist.get_metrics_summary()
                
                # Save the artist to persist onFireStatus
                artist.save(update_fields=['onFireStatus'])
                
                if metrics_summary.get('on_fire', False):
                    on_fire_count += 1
                    
                updated += 1
                
            except Exception as e:
                logger.error(f"Error updating metrics for artist {artist.id}: {str(e)}", exc_info=True)
                capture_exception(e)
        
        return {
            'status': 'completed',
            'updated': updated,
            'on_fire_count': on_fire_count,
            'date': date.today().isoformat(),
            'message': f'Updated metrics for {updated} artists. {on_fire_count} artists are on fire.'
        }
        
    except Exception as e:
        error_msg = f"Error in update_daily_metrics: {str(e)}"
        logger.error(error_msg, exc_info=True)
        capture_exception(e)
        return {
            'status': 'error',
            'error': str(e),
            'message': 'Failed to update metrics'
        }

def update_artist_metrics(artist_id=None, force_update=False, retry_count=0):
    """
    Update artist metrics from SoundCharts and calculate buzz scores.
    
    This function will:
    1. Update artist metrics from SoundCharts API
    2. Recalculate the buzz score based on the latest metrics
    3. Update the artist's performance tier if needed
    
    Args:
        artist_id (int, optional): Specific artist ID to update. If None, updates all artists.
        force_update (bool): If True, forces update even if recently updated.
        retry_count (int): Number of retry attempts made so far
    
    Returns:
        dict: Result of the update operation with counts and status
    """
    try:
        # Get the base queryset
        queryset = Artist.objects.all()
        if artist_id is not None:
            queryset = queryset.filter(id=artist_id)
            logger.info(f"[DEBUG] Filtering for specific artist ID: {artist_id}")
        else:
            # For all artists, we'll still try to update them even without a SoundCharts UUID
            # as the method will handle the missing UUID case
            logger.info("[DEBUG] No artist ID provided, will process all artists")
            pass  # Don't filter out artists without UUID, let the method handle it
        
        # Filter out artists that were recently updated if not forcing
        if not force_update:
            min_update_time = timezone.now() - timedelta(hours=MIN_UPDATE_INTERVAL)
            queryset = queryset.filter(
                Q(last_metrics_update__isnull=True) | 
                Q(last_metrics_update__lt=min_update_time)
            )
            logger.info(f"[DEBUG] Filtered out artists updated in the last {MIN_UPDATE_INTERVAL} hours")
        else:
            logger.info("[DEBUG] Force update enabled, including all artists regardless of last update time")      
        
        total_artists = queryset.count()
        if total_artists == 0:
            if artist_id is not None:
                logger.info(f'No artist found with ID {artist_id} or already up to date')
            else:
                logger.info('No artists to update or all artists are up to date')
            return {'status': 'success', 'message': 'No artists to update', 'updated': 0}
        
        updated_count = 0
        skipped_count = 0
        errors = 0
        
        logger.info(f'Starting metrics update for {total_artists} artists')
        
        # Process artists in batches to avoid memory issues
        for i in range(0, total_artists, BATCH_SIZE):
            batch = queryset[i:i + BATCH_SIZE]
            for artist in batch:
                try:
                    with transaction.atomic():
                        # Log artist details for debugging
                        logger.info(f"[DEBUG] Processing artist ID: {artist.id}, Name: {artist.band_name or getattr(artist.user, 'name', 'N/A')}, SoundCharts UUID: {artist.soundcharts_uuid}")
                        
                        # Don't skip if no SoundCharts UUID, let the method handle it
                        # The method will log and handle the missing UUID case appropriately
                            
                        # Update metrics from SoundCharts with debug logging
                        logger.info(f"[DEBUG] Calling update_metrics_from_soundcharts for artist {artist.id}")
                        result = artist.update_metrics_from_soundcharts(force_update=force_update)
                        logger.info(f"[DEBUG] Result from update_metrics_from_soundcharts for artist {artist.id}: {result}")
                        
                        if result.get('success', False):
                            updated_count += 1
                            logger.debug(f'Updated metrics for artist {artist.id}: {artist.band_name or artist.user.name}')
                        else:
                            error_msg = result.get('message', 'Unknown error')
                            if result.get('code') == 'missing_uuid':
                                logger.debug(f'Skipping artist {artist.id}: {error_msg}')
                                skipped_count += 1
                            else:
                                logger.warning(
                                    f'Failed to update metrics for artist {artist.id} ({artist.band_name or artist.user.name}): ' 
                                    f"{error_msg}"
                                )
                                errors += 1
                            
                except Exception as e:
                    error_msg = f'Error updating artist {artist.id}: {str(e)}'
                    logger.error(error_msg, exc_info=True)
                    capture_exception(e)
                    errors += 1
        
        # Prepare summary
        result = {
            'status': 'success',
            'updated': updated_count,
            'skipped': skipped_count,
            'errors': errors,
            'total_processed': updated_count + skipped_count + errors,
            'total_artists': total_artists,
            'timestamp': timezone.now().isoformat()
        }
        
        # Log summary
        logger.info(
            'Artist metrics update completed. ' +
            f'Updated: {updated_count}, ' +
            f'Skipped: {skipped_count}, ' +
            f'Errors: {errors}, ' +
            f'Total: {total_artists}'
        )
        
        return result
        
    except Exception as e:
        error_msg = f'Critical error in update_artist_metrics task: {str(e)}'
        logger.error(error_msg, exc_info=True)
        capture_exception(e)
        
        # Only retry if we haven't exceeded max retries
        if self.request.retries < MAX_RETRIES:
            retry_in = RETRY_DELAY * (self.request.retries + 1)  # Exponential backoff
            logger.info(f'Retrying task in {retry_in} seconds (attempt {self.request.retries + 1}/{MAX_RETRIES})')
            raise self.retry(exc=e, countdown=retry_in)
            
        # If we've exceeded max retries, log and return error
        logger.error(f'Max retries exceeded for update_artist_metrics task: {str(e)}')
        return {
            'status': 'error',
            'message': str(e),
            'retries_exceeded': True
        }

def schedule_daily_metrics_update():
    """
    Function to update all artists' metrics and daily tracking.
    This should be called once per day as a scheduled task.
    
    This function will:
    1. Update all artists' metrics from SoundCharts
    2. Record daily metrics for trend analysis
    3. Update 'on fire' status based on daily buzz score changes
    
    Returns:
        dict: Summary of the update operation with counts and status
    """
    try:
        # First, update all artists' metrics
        metrics_result = update_artist_metrics()
        
        # Then, update daily metrics and check for 'on fire' status
        daily_result = update_daily_metrics()
        
        # Combine results
        result = {
            'status': 'success',
            'metrics_updated': metrics_result.get('updated', 0),
            'metrics_skipped': metrics_result.get('skipped', 0),
            'metrics_errors': metrics_result.get('errors', 0),
            'daily_updated': daily_result.get('updated', 0),
            'on_fire_count': daily_result.get('on_fire_count', 0),
            'date': date.today().isoformat(),
            'timestamp': timezone.now().isoformat()
        }
        
        logger.info(
            'Daily metrics update completed. ' +
            f'Metrics updated: {result["metrics_updated"]}, ' +
            f'Daily records: {result["daily_updated"]}, ' +
            f'Artists on fire: {result["on_fire_count"]}'
        )
        
        return result
            
    except Exception as e:
        error_msg = f'Critical error in schedule_daily_metrics_update: {str(e)}'
        logger.error(error_msg, exc_info=True)
        capture_exception(e)
        
        return {
            'status': 'error',
            'message': str(e),
            'metrics_updated': 0,
            'daily_updated': 0,
            'on_fire_count': 0,
            'date': date.today().isoformat()
        }

def update_artist_metrics_on_save(sender, instance, created, **kwargs):
    """
    Signal handler to update metrics when an artist is created or has relevant fields updated.
    
    This will be connected to the post_save signal for the Artist model.
    """
    # Only proceed if this is a new artist or if relevant fields were updated
    if created or any(field in ['soundcharts_uuid', 'instagram_followers', 
                              'tiktok_followers', 'spotify_followers', 
                              'youtube_subscribers'] for field in instance.get_dirty_fields()):
        try:
            # Run the update in a background thread
            run_async(update_artist_metrics, artist_id=instance.id)
        except Exception as e:
            logger.error(f"Error scheduling metrics update for artist {instance.id}: {str(e)}")
            capture_exception(e)
