import json
import os
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

# Configure Django settings if not already configured
if not settings.configured:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gigspot_backend.settings')

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close()
        else:
            self.user = self.scope["user"]
            self.room_group_name = f"notifications_{self.user.id}"
            
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        try:
            # Debug: Log the raw incoming message
            print(f"Raw WebSocket message received: {text_data}")
            
            # Clean the input if needed
            if isinstance(text_data, bytes):
                text_data = text_data.decode('utf-8')
                
            # Remove any null bytes or other problematic characters
            text_data = text_data.strip('\x00')
            
            # Try to parse the JSON
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError as e:
                # Try to find where the error is occurring
                print(f"JSON decode error at position {e.pos}: {e.doc}")
                print(f"Context: {e.doc[max(0, e.pos-20):min(len(e.doc), e.pos+20)]}")
                raise
                
            if not isinstance(data, dict):
                raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
                
            message_type = data.get('type')
            if not message_type:
                raise ValueError("Missing 'type' in message")
                
            if message_type == 'read_notification':
                notification_id = data.get('notification_id')
                if not notification_id:
                    raise ValueError("Missing 'notification_id' in read_notification message")
                await self.mark_notification_as_read(notification_id)
            elif message_type == 'notification':
                notification_data = data.get('notification')
                if not notification_data:
                    raise ValueError("Missing 'notification' data in message")
                if not isinstance(notification_data, dict):
                    raise ValueError("Notification data must be an object")
                await self.notification(notification_data)
            else:
                raise ValueError(f"Unknown message type: {message_type}")
                
        except json.JSONDecodeError as e:
            error_msg = {
                'type': 'error',
                'message': 'Invalid JSON format',
                'details': str(e),
                'received': text_data[:100]  # Include first 100 chars of received data
            }
            print(f"JSON decode error: {error_msg}")
            await self.send(text_data=json.dumps(error_msg))
            
        except ValueError as e:
            error_msg = {
                'type': 'error',
                'message': 'Invalid message format',
                'details': str(e)
            }
            print(f"Value error: {error_msg}")
            await self.send(text_data=json.dumps(error_msg))
            
        except Exception as e:
            error_msg = {
                'type': 'error',
                'message': 'Error processing message',
                'details': str(e),
                'error_type': type(e).__name__
            }
            print(f"Unexpected error: {error_msg}")
            await self.send(text_data=json.dumps(error_msg))

    async def notification(self, event):
        try:
            # Handle both direct content and nested content formats
            content = event.get('content', event)
            
            # Send notification to WebSocket
            await self.send(text_data=json.dumps({
                'type': 'notification',
                'notification': {
                    'message': content.get('message', ''),
                    'description': content.get('description', ''),
                    'notification_type': content.get('notification_type', ''),
                    # Add any other fields you expect
                }
            }))
        except Exception as e:
            print(f"Error processing notification: {e}")
            # Optionally send an error message to the client
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to process notification'
            }))

    @database_sync_to_async
    def mark_notification_as_read(self, notification_id):
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient=self.user
            )
            notification.is_read = True
            notification.save()
        except Notification.DoesNotExist:
            pass
