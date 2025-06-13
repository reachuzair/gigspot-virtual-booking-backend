from django.urls import path
from social_auth.views import  google_login

urlpatterns = [
    path("auth/google/", google_login, name="google_login"),
]
