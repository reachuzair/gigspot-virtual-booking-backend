from django.urls import path
from .views import (update_profile, update_user_profile, user_profile, 
                     update_profile_image, update_notification_settings, 
                     update_artist_soundcharts_uuid, get_artist_metrics)

urlpatterns = [
    path('profile/', user_profile, name='user_profile'),
    path('profile/image/', update_profile_image, name='update_profile_image'),
    path('notification-settings/', update_notification_settings,
         name='update_notification_settings'),
    path('artist/soundcharts-uuid/', update_artist_soundcharts_uuid,
         name='update_artist_soundcharts_uuid'),
    path('profile/update/', update_profile, name='update-user-profile'),
    path('artist/metrics/', get_artist_metrics, name='get_artist_metrics'),

]
