from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

urlpatterns = [
    path('', views.list_notifications, name='list_notifications'),
    path('create/', views.create_notification,
         name='create_notification'),
    path('mark_all_as_read/',
         views.mark_all_as_read, name='mark_all_as_read'),
    path('email/', views.SendEmailView.as_view(), name='email_notifications'),
]
