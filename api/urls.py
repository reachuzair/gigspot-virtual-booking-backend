from django.urls import path
from .views import hello_test

urlpatterns = [
    path('hello/', hello_test, name='hello_test'),
]