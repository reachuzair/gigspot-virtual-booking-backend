
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.apple.views import AppleOAuth2Adapter
from django.urls import path

from social_auth.views import CustomAppleLogin, CustomGoogleLogin


urlpatterns = [
    path("auth/apple/", CustomAppleLogin.as_view(), name="apple_login"),
    path('auth/google/', CustomGoogleLogin.as_view(), name='custom_google_login'),
]
