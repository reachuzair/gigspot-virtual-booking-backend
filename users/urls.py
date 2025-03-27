from django.urls import path
from .views import user_profile, update_profile_image

urlpatterns = [
    path('profile/', user_profile, name='user_profile'),
    path('profile/image/', update_profile_image, name='update_profile_image')
]