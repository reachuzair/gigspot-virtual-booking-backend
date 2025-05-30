from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'notification_type', 'title',
                  'message', 'is_read','created_at', 'recipient']
        read_only_fields = ['created_at']


class EmailSerializer(serializers.Serializer):
    subject = serializers.CharField()
    message = serializers.CharField()
    to = serializers.ListField(child=serializers.EmailField())
    attachment = serializers.FileField(required=False)
    
