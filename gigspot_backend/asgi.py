"""
ASGI config for gigspot_backend project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/howto/deployment/asgi/
"""
import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gigspot_backend.settings')

django.setup() 

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.urls import path
from rt_notifications.consumers import NotificationConsumer
from chat.consumers import ChatConsumer



application = ProtocolTypeRouter({
    'http': get_asgi_application(),
    'websocket': AuthMiddlewareStack(
        URLRouter([
            path("ws/chat/<int:room_id>/", ChatConsumer.as_asgi()),
            path("ws/notifications/", NotificationConsumer.as_asgi()),
           
        ])
    ),
})
