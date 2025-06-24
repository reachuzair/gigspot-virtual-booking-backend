from django.apps import AppConfig
from django.db.models.signals import post_save


def update_artist_metrics_on_save(sender, instance, created, **kwargs):
    """
    Signal handler to update metrics when an artist is created or updated.
    """
    from .tasks import update_artist_metrics
    if created or instance.last_metrics_update is None or \
       (instance._state.db and 
        (instance._state.adding or 
         instance.tracker.has_changed('instagram_followers') or
         instance.tracker.has_changed('tiktok_followers') or
         instance.tracker.has_changed('spotify_followers') or
         instance.tracker.has_changed('youtube_subscribers') or
         instance.tracker.has_changed('playlist_views') or
         instance.tracker.has_changed('engagement_rate'))):
        update_artist_metrics.delay(artist_id=instance.id)


class ArtistsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'artists'
    
    def ready(self):
        # Import here to avoid AppRegistryNotReady error
        from django.db.models.signals import post_save
        from custom_auth.models import Artist
        
        # Connect the signal
        post_save.connect(update_artist_metrics_on_save, sender=Artist)
