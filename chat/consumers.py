import json
import logging
import os
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import ChatRoom, Message, MessageReadStatus

# Set up logging
logger = logging.getLogger(__name__)

# Ensure Django settings are configured
if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gigspot_backend.settings')

class ChatConsumer(AsyncWebsocketConsumer):
    
    async def connect(self):
        """Handle new WebSocket connection with validation and error handling."""
        try:
            self.room_id = self.scope['url_route']['kwargs']['room_id']
            self.user = self.scope["user"]
            
            if self.user.is_anonymous:
                await self.close(code=4003)  # Forbidden
                return

            # Validate room and permissions
            self.room = await self.get_room()
            if not self.room:
                await self.close(code=4004)  # Room not found
                return

            if not await self.is_user_participant():
                await self.close(code=4003)  # Forbidden
                return

            self.room_group_name = f'chat_{self.room_id}'
            
            # Add to room group
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.accept()
            
            # Notify others in the room
            await self.notify_user_status('online')
            
        except Exception as e:
            logger.error(f"Connection error: {str(e)}")
            await self.close(code=4000)  # Internal error

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
            if hasattr(self, 'user'):
                await self.notify_user_status('offline')

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get('type', 'chat_message')
            
            if message_type == 'typing':
                await self.handle_typing(data)
            elif message_type == 'read_receipt':
                await self.handle_read_receipt(data)
            else:
                await self.handle_chat_message(data)
                
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON format")
        except Exception as e:
            logger.error(f"Message handling error: {str(e)}")
            await self.send_error("Error processing message")

    async def handle_chat_message(self, data):
        """Process and broadcast chat messages."""
        content = data.get('message')
        if not content:
            await self.send_error("Message content is required")
            return

        try:
            # Get room type and participants
            room_type = await self.get_room_type()
            participants = await self.get_room_participants()
            
            # For private chat, find the other participant
            receiver = None
            if room_type == 'private':
                receiver = next((p for p in participants if p != self.user), None)
                if not receiver:
                    await self.send_error("No receiver found in private chat")
                    return
            
            # Save the message
            message = await self.save_message(content, receiver.id if receiver else None)
            
            # Prepare message data
            message_data = {
                'type': 'chat_message',
                'message_id': str(message.id),
                'content': content,
                'sender_id': str(self.user.id),
                'sender_name': await self.get_user_name(self.user.id),
                'room_id': str(self.room_id),
                'room_type': room_type,
                'timestamp': message.timestamp.isoformat(),
                'status': 'sent'
            }
            
            # For private chat, add receiver info
            if receiver:
                message_data['receiver_id'] = str(receiver.id)
                message_data['receiver_name'] = await self.get_user_name(receiver.id)
            
            # Send to sender
            await self.send(text_data=json.dumps(message_data))
            
            # Send to other participants
            for participant in participants:
                if participant != self.user:  # Don't send to self again
                    await self.channel_layer.group_send(
                        f'user_{participant.id}',
                        {
                            'type': 'chat_message',
                            **message_data,
                            'status': 'delivered' if participant == receiver else 'sent'
                        }
                    )
            
            # Update status to delivered for direct messages
            if receiver:
                await self.update_message_status(message.id, 'delivered')

        except Exception as e:
            logger.error(f"Message save error: {str(e)}")
            await self.send_error("Failed to send message")

    async def handle_typing(self, data):
        """Handle typing indicators."""
        is_typing = data.get('is_typing', False)
        receiver_id = data.get('receiver_id')
        
        if not receiver_id:
            return
            
        await self.channel_layer.group_send(
            f'user_{receiver_id}',
            {
                'type': 'typing_indicator',
                'user_id': str(self.user.id),
                'is_typing': is_typing
            }
        )

    async def handle_read_receipt(self, data):
        """Handle read receipts."""
        message_id = data.get('message_id')
        if message_id:
            await self.mark_message_as_read(message_id)

    async def chat_message(self, event):
        """Send chat message to WebSocket."""
        await self.send(text_data=json.dumps(event))
        
    async def user_status(self, event):
        """Handle user status updates."""
        # Forward the status update to the client
        await self.send(text_data=json.dumps({
            'type': 'user_status',
            'user_id': event['user_id'],
            'status': event['status']
        }))
        
    async def typing_indicator(self, event):
        """Send typing status to client."""
        if str(self.user.id) != event['user_id']:  # Don't send to the typer
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'user_id': event['user_id'],
                'is_typing': event['is_typing']
            }))

    @database_sync_to_async
    def get_room(self):
        try:
            return ChatRoom.objects.get(id=self.room_id)
        except ChatRoom.DoesNotExist:
            return None
        
    @database_sync_to_async
    def is_user_participant(self):
        """Check if user is a participant in the room."""
        return self.room.participants.filter(id=self.user.id).exists()
        
    @database_sync_to_async
    def get_room_type(self):
        """Get the type of the room."""
        return self.room.room_type
        
    @database_sync_to_async
    def get_room_participants(self):
        """Get all participants in the room."""
        return list(self.room.participants.all())
        
    async def notify_user_status(self, status):
        """Notify room about user status change."""
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_status',
                'user_id': str(self.user.id),
                'status': status
            }
        )
    async def send_error(self, message):
        """Send error message to client."""
        await self.send(text_data=json.dumps({
            'type': 'error',
            'message': message
        }))

    @database_sync_to_async
    def save_message(self, content, receiver_id=None):
        """Save message to database with immediate commit."""
        from django.contrib.auth import get_user_model
        from django.db import transaction
        from django.core.cache import cache
        import time
        
        User = get_user_model()
        
        def invalidate_room_cache(room_id):
            """Invalidate all cached messages for a specific room"""
            # This will clear all pages of messages for this room
            cache.delete_many(
                cache.keys(f'messages_*_room_{room_id}_page_*')
            )
        
        with transaction.atomic():
            # Get or create room based on participants
            if receiver_id:
                # Private chat
                receiver = User.objects.get(id=receiver_id)
                room, created = ChatRoom.objects.get_or_create(
                    room_type='private',
                    defaults={'name': f'Chat {self.user.id}-{receiver_id}'}
                )
                if created:
                    room.participants.add(self.user, receiver)
                    room.save()  # Ensure room is saved before using it
            else:
                # Group chat - use existing room
                room = self.room
            
            # Create and save the message
            message = Message.objects.create(
                chat_room=room,
                sender=self.user,
                content={"text": content},
                receiver_id=receiver_id
            )
            
            # Update the room's updated_at timestamp
            ChatRoom.objects.filter(id=room.id).update(updated_at=message.timestamp)
            
            # Invalidate cache for this room
            transaction.on_commit(lambda: invalidate_room_cache(room.id))
            
            # Small delay to ensure database commit
            time.sleep(0.1)
            
            # Explicitly refresh from database
            message.refresh_from_db()
            return message

    @database_sync_to_async
    def get_user_name(self, user_id):
        """Get user's display name."""
        from django.contrib.auth import get_user_model
        try:
            user = get_user_model().objects.get(id=user_id)
            return user.name or user.email.split('@')[0]
        except Exception as e:
            logger.error(f"Error getting user name: {str(e)}")
            return 'Unknown User'
    @database_sync_to_async
    def update_message_status(self, message_id, status):
        """Update message delivery status."""
        try:
            message = Message.objects.get(id=message_id)
            if status == 'delivered':
                # For delivered status, we don't need to update anything
                # as we only track read status explicitly
                pass
            elif status == 'read':
                message.is_read = True
                message.read_at = timezone.now()
                message.save(update_fields=['is_read', 'read_at'])
        except Message.DoesNotExist:
            logger.warning(f"Message {message_id} not found for status update")
            
    @database_sync_to_async
    def mark_message_as_read(self, message_id):
        """Mark a message as read."""
        try:
            message = Message.objects.get(
                id=message_id,
                receiver=self.user,
                is_read=False
            )
            message.is_read = True
            message.read_at = timezone.now()
            message.save(update_fields=['is_read', 'read_at'])
        except Message.DoesNotExist:
            logger.warning(f"Message {message_id} not found for read receipt or already read")

