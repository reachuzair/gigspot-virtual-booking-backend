import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf  import settings
from .models import ChatRoom, Message

if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gigspot_backend.settings')

class ChatConsumer(AsyncWebsocketConsumer):
    print("ChatConsumer initialized")
    async def connect(self):    
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'
        print(f"Connecting to room: {self.room_group_name}")
        if self.scope["user"].is_anonymous:
            print("Anonymous user trying to connect")
            await self.close()
            return
        
        print("Authenticated user connecting")
        self.user = self.scope["user"]
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'chat_{self.room_id}'

       
        room = await self.get_room()
        is_participant = await self.is_user_participant(room)
        if not room or not is_participant:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        content = data.get('message')

        if content:
            message = await self.save_message(content)

            # Broadcast to room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message': content,
                    'sender_id': self.user.id,
                    # 'sender_username': self.user.username,
                    'timestamp': str(message.timestamp),
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat',
            'message': event['message'],
            'sender_id': event['sender_id'],
            # 'sender_username': event['sender_username'],    
            'timestamp': event['timestamp'],
        }))

    @database_sync_to_async
    def get_room(self):
        try:
            return ChatRoom.objects.get(id=self.room_id)
        except ChatRoom.DoesNotExist:
            return None
        
    @database_sync_to_async
    def is_user_participant(self, room):
        return self.user in room.participants.all()
    
    @database_sync_to_async
    def save_message(self, content):
        return Message.objects.create(
            chat_room_id=self.room_id,
            sender=self.user,
            content={"text": content}
        )
