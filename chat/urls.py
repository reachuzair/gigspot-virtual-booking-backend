from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    CreateChatRoomView, 
    DeleteMessageView,
    InboxView,
    MarkMessagesAsReadView
)
from .email_urls import urlpatterns as email_urls

app_name = 'chat'

# API endpoints
urlpatterns = [
    # Chat endpoints
    path('create/', CreateChatRoomView.as_view(), name='create-chat-room'),
    path('inbox/', InboxView.as_view(), name='inbox'),
    path('messages/delete/', DeleteMessageView.as_view(), name='delete-message'),
    path('messages/mark-read/', MarkMessagesAsReadView.as_view(), name='mark-messages-read'),
    
    # Email endpoints
    path('emails/', include((email_urls, 'email_api'))),
]

