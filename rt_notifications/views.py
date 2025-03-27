from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification
from .serializers import NotificationSerializer

class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    def perform_create(self, serializer):
        notification = serializer.save(recipient=self.request.user)
        self._send_notification_to_websocket(notification)

    @action(detail=False, methods=['post'])
    def mark_all_as_read(self, request):
        self.get_queryset().update(is_read=True)
        return Response(status=status.HTTP_200_OK)

    def _send_notification_to_websocket(self, notification):
        channel_layer = get_channel_layer()
        notification_data = NotificationSerializer(notification).data
        
        async_to_sync(channel_layer.group_send)(
            f'notifications_{notification.recipient.id}',
            {
                'type': 'notification',
                'notification': notification_data
            }
        )
