from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action,permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import api_view
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification
from .serializers import NotificationSerializer

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def list_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')  # optional: newest first

    paginator = PageNumberPagination()
    paginated_qs = paginator.paginate_queryset(notifications, request)
    serializer = NotificationSerializer(paginated_qs, many=True)

    return paginator.get_paginated_response(serializer.data)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def create_notification(request):
    serializer = NotificationSerializer(data=request.data)
    if serializer.is_valid():
        notification = serializer.save(recipient=request.user)
        _send_notification_to_websocket(notification)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def mark_all_as_read(request):
    Notification.objects.filter(recipient=request.user).update(is_read=True)
    return Response(status=status.HTTP_200_OK)


def _send_notification_to_websocket(notification):
    channel_layer = get_channel_layer()
    notification_data = NotificationSerializer(notification).data

    async_to_sync(channel_layer.group_send)(
        f'notifications_{notification.recipient.id}',
        {
            'type': 'notification',
            'notification': notification_data
        }
    )

    
