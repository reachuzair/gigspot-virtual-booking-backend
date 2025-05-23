from django.urls import path
from .views import hello_test
from chat.views import ChatRoomCreateView , CreateChatRoomView

urlpatterns = [
    path('hello/', hello_test, name='hello_test'),
    path('chat-rooms/', ChatRoomCreateView.as_view(), name='chatroom-create'),
    path('create-chat/', CreateChatRoomView.as_view(), name='create_chat_room'),
]