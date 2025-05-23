from rest_framework import serializers
from .models import ChatRoom
from django.conf import settings
from django.contrib.auth import get_user_model
User = get_user_model()

class ChatRoomSerializer(serializers.ModelSerializer):
    participant_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), write_only=True, source='participants'
    )

    class Meta:
        model = ChatRoom
        fields = ['id', 'participant_ids', 'created_at']
        read_only_fields = ['id', 'created_at']

    def create(self, validated_data):
        participants = validated_data.pop('participants')
        room = ChatRoom.objects.create(**validated_data)
        room.participants.set(participants)
        return room
 