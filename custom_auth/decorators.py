from functools import wraps
from django.http import JsonResponse
from django.utils import timezone
from .models import Artist
from .utils import update_artist_metrics_if_needed

def update_artist_metrics(view_func):
    """
    Decorator to update artist metrics before serving the view.
    Only updates if the user is an artist and has a SoundCharts UUID.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)
        
        # Only process if the request was successful and user is authenticated
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                if hasattr(request.user, 'artist') and request.user.artist.soundcharts_uuid:
                    update_artist_metrics_if_needed(request.user.artist)
            except Artist.DoesNotExist:
                pass
                
        return response
    return _wrapped_view
