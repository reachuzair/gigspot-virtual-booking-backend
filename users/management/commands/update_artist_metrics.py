import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Q
from custom_auth.models import Artist
from artists.tasks import update_artist_metrics, schedule_daily_metrics_update

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Update artist metrics from SoundCharts API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force update even if recently updated',
        )
        parser.add_argument(
            '--artist-id',
            type=int,
            help='Update a specific artist by ID',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=50,
            help='Number of artists to process in each batch (default: 50)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without making any changes',
        )

    def handle(self, *args, **options):
        verbosity = options.get('verbosity', 1)
        force = options.get('force', False)
        artist_id = options.get('artist_id')
        batch_size = options.get('batch_size', 50)
        dry_run = options.get('dry_run', False)

        # Set up logging based on verbosity
        if verbosity > 1:
            logger.setLevel(logging.DEBUG)
        elif verbosity > 0:
            logger.setLevel(logging.INFO)
        else:
            logger.setLevel(logging.WARNING)

        logger.info("Starting artist metrics update" + (" (dry run)" if dry_run else ""))
        logger.debug(f"Options: {options}")

        try:
            if dry_run:
                logger.info("Dry run - no changes will be made")
                queryset = Artist.objects.all()
                if artist_id:
                    queryset = queryset.filter(id=artist_id)
                
                count = queryset.count()
                logger.info(f"Would update metrics for {count} artists")
                return

            if artist_id:
                # Update a specific artist
                logger.info(f"Updating metrics for artist ID: {artist_id}")
                result = update_artist_metrics(artist_id=artist_id, force_update=force)
                
                # Log detailed results
                if result.get('status') == 'success':
                    logger.info(
                        f"Successfully updated {result.get('updated', 0)} artists. "
                        f"Skipped: {result.get('skipped', 0)}, "
                        f"Errors: {result.get('errors', 0)}"
                    )
                else:
                    logger.error(f"Failed to update artist metrics: {result.get('message', 'Unknown error')}")
                    
            else:
                # Update all artists using the scheduled update function
                logger.info("Starting daily metrics update for all artists")
                result = schedule_daily_metrics_update()
                
                # Log summary of the scheduled update
                if result and result.get('status') == 'success':
                    logger.info(
                        f"Scheduled update completed. "
                        f"Updated: {result.get('updated', 0)}, "
                        f"Skipped: {result.get('skipped', 0)}, "
                        f"Errors: {result.get('errors', 0)}"
                    )
                else:
                    error_msg = result.get('message', 'Unknown error') if result else 'No result returned'
                    logger.error(f"Failed to schedule daily update: {error_msg}")

        except Exception as e:
            logger.error(f"Error updating artist metrics: {str(e)}", exc_info=True)
            self.stderr.write(self.style.ERROR(f'Error: {str(e)}'))
            raise

        logger.info("Artist metrics update process completed")
