from django.urls import path
from .views import hello_test
from chat.views import ChatRoomCreateView , CreateChatRoomView, MessageListView, DeleteMessageView

urlpatterns = [
    path('hello/', hello_test, name='hello_test'),
    path('chat-rooms/', ChatRoomCreateView.as_view(), name='chatroom-create'),
    path('create-chat/', CreateChatRoomView.as_view(), name='create_chat_room'),
    path("messages/<int:room_id>/", MessageListView.as_view(), name="get_room_messages"),
    path("messages/delete/<int:message_id>/", DeleteMessageView.as_view(), name="delete_message"),    
]