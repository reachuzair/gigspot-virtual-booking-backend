from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()

urlpatterns = [
    path('', include(router.urls)),
    path('notifications/', views.list_notifications, name='list_notifications'),
    path('notifications/create/', views.create_notification,
         name='create_notification'),
    path('notifications/mark_all_as_read/',
         views.mark_all_as_read, name='mark_all_as_read'),
]
