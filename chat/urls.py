# urls.py (inside your app)
from django.urls import path
from .views import ChatRoomCreateView, CreateChatRoomView

urlpatterns = [
    path('chat-rooms/', ChatRoomCreateView.as_view(), name='chatroom-list'),
    path("create-chat/", CreateChatRoomView.as_view(), name="create_chat_room"),
]
