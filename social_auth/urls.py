from django.urls import path
from social_auth.views import  apple_login, google_login

urlpatterns = [
    path("auth/google/", google_login, name="google_login"),
    path('auth/apple/', apple_login),
]
