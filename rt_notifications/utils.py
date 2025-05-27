from django.contrib.auth.models import User
from notifications.signals import notify
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .helpers import send_notify_templated_email

def create_notification(user, notification_type, message, **kwargs):
    """
    Create a notification and send it via WebSocket.
    """

    if user.settings.notify_by_app:
        # Create the notification
        notify.send(
            user,
            recipient=user,
            notification_type=notification_type,
            verb=message,
            **kwargs
        )
        # print(f"Notification sent to {user.name}: {message}")
        # Send real-time notification via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"notifications_{user.id}",
            {
                "type": "notification",  # This must match the consumer method name
                "content": {  # This matches what the consumer expects
                    "message": message,
                    "description": kwargs.get('description', ''),
                    "notification_type": notification_type,
                    # Include any other fields your consumer expects
                },
            }
        )
    # print(f"Notification created for {user.name}: {message}")
    if user.settings.notify_by_email:
        send_notify_templated_email(user.email, notification_type, message, **kwargs)
        print(f"Email notification sent to {user.email}: {message}")