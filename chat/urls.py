# urls.py (inside your app)
from django.urls import path
from .views import ChatRoomCreateView, CreateChatRoomView, MessageListView, DeleteMessageView

urlpatterns = [
    path('chat-rooms/', ChatRoomCreateView.as_view(), name='chatroom-list'),
    path("create-chat/", CreateChatRoomView.as_view(), name="create_chat_room"),
      path("messages/<int:room_id>/", MessageListView.as_view(), name="get_room_messages"),
    path("messages/delete/<int:message_id>/", DeleteMessageView.as_view(), name="delete_message"),
]

