from django.urls import path
from .views import hello_test
from chat.views import  CreateChatRoomView,get_messages, DeleteMessageView,InboxView, MarkMessagesAsReadView

urlpatterns = [
    path('hello/', hello_test, name='hello_test'),
    path('create-chat/', CreateChatRoomView.as_view(), name='create_chat_room'),
    path("messages/<int:room_id>/", get_messages, name="get_messages"),
    path("messages/delete/", DeleteMessageView.as_view(), name="delete_message"),    
    path("inbox/", InboxView.as_view(), name="chat_inbox"),
    path("messages/mark-read/", MarkMessagesAsReadView.as_view(), name="mark_messages_read"),
]