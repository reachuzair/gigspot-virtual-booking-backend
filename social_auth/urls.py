
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from django.urls import path

from social_auth.views import  google_login
from django.urls import include as iclude

urlpatterns = [
    # path("auth/apple/", CustomAppleLogin.as_view(), name="apple_login"),
    # path('auth/google/', CustomGoogleLogin.as_view(), name='custom_google_login'),
    # path('allauth/', iclude('allauth.urls'))
    path("auth/google/", google_login, name="google_login"),
    
]
