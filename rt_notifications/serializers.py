from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    recipient_name = serializers.CharField(
        source='recipient.name', read_only=True)
    recipient_profile_picture = serializers.ImageField(
        source='recipient.profileImage', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'notification_type', 'title',
                  'message', 'is_read', 'created_at', 'recipient', 'recipient_name','recipient_profile_picture']
        read_only_fields = ['created_at']


class EmailSerializer(serializers.Serializer):
    subject = serializers.CharField()
    message = serializers.CharField()
    to = serializers.ListField(child=serializers.EmailField())
    attachment = serializers.FileField(required=False)
