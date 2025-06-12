from .views import (
    analytics_overview,
    fan_engagement_stats,
    ticket_analytics
)
from django.urls import path
urlpatterns = [
    path('overview/', analytics_overview),
    path('fan-engagement/', fan_engagement_stats),
    path('ticket-analytics/', ticket_analytics, name='ticket-analytics'),
]
