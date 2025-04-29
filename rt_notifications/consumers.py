import json
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
        data = json.loads(text_data)
        if data.get('type') == 'read_notification':
            notification_id = data.get('notification_id')
            await self.mark_notification_as_read(notification_id)
        elif data.get('type') == 'notification':
            notification_data = data.get('notification')
            await self.notification(notification_data)

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
