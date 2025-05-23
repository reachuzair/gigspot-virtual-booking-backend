# urls.py (inside your app)
from django.urls import path
from .views import ChatRoomCreateView

urlpatterns = [
    path('chat-rooms/', ChatRoomCreateView.as_view(), name='chatroom-create'),
]
