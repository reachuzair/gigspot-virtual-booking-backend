from django.contrib import admin
from .models import ChatRoom, Message, MessageReadStatus

@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('id', 'room_type', 'name', 'created_at')
    filter_horizontal = ('participants',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_room', 'sender', 'receiver', 'timestamp', 'is_read')


@admin.register(MessageReadStatus)
class MessageReadStatusAdmin(admin.ModelAdmin):
    list_display = ('id', 'message', 'user', 'is_read', 'read_at')
