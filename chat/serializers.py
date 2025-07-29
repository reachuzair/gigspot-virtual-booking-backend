from rest_framework import serializers

from custom_auth.serializers import UserSerializer
from .models import ChatRoom, Message, EmailThread, EmailMessage, EmailAttachment, EmailThreadParticipant
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.exceptions import ValidationError
from django.utils import timezone
import os

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


class MessageSerializer(serializers.ModelSerializer):
    # sender_username = serializers.CharField(source='sender.name', read_only=True)
    # receiver_id = serializers.IntegerField(source='receiver.id', allow_null=True, read_only=True)
    sender = UserSerializer(read_only=True)
    receiver = UserSerializer(read_only=True)
    attachment_url = serializers.SerializerMethodField()
    

    class Meta:
        model = Message
        fields = [
            'id', 'sender',  'receiver',
            'content', 'timestamp', 'is_read',
            'attachment_url'
        ]
    def get_profile_image(self, obj):
        """Get the profile image URL of the sender"""
        if obj.sender and obj.sender.profile_image:
            return obj.sender.profile_image.url
        return None

    def get_attachment_url(self, obj):
        return obj.attachment.url if obj.attachment else None



class EmailAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for email attachments"""
    file_name = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()
    file_type = serializers.SerializerMethodField()

    class Meta:
        model = EmailAttachment
        fields = ['id', 'file_name', 'file_size', 'file_type', 'created_at']
        read_only_fields = ['id', 'created_at']

    def get_file_name(self, obj):
        return os.path.basename(obj.file.name)

    def get_file_size(self, obj):
        try:
            return obj.file.size
        except (FileNotFoundError, ValueError):
            return 0

    def get_file_type(self, obj):
        return os.path.splitext(obj.file.name)[1].lstrip('.').lower()


class EmailMessageSerializer(serializers.ModelSerializer):
    """Serializer for email messages"""
    sender_name = serializers.CharField(source='sender.name', read_only=True)
    sender_email = serializers.EmailField(source='sender.email', read_only=True)
    to_recipients = serializers.PrimaryKeyRelatedField(
        many=False,  # Changed to False for one-to-one
        queryset=User.objects.all(),
        write_only=True,
        required=True
    )
    cc_recipients = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), many=True)
    
    def validate(self, attrs):
        # Get or initialize cc_recipients
        cc_recipients = attrs.get('cc_recipients', [])
        if not isinstance(cc_recipients, list):
            cc_recipients = [cc_recipients] if cc_recipients else []
            
        # Add admin to CC if not already present
        admin_user = User.objects.filter(is_superuser=True).first()
        if admin_user and admin_user not in cc_recipients:
            cc_recipients.append(admin_user)
            
        attrs['cc_recipients'] = cc_recipients
        return attrs
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    uploaded_files = serializers.ListField(
        child=serializers.FileField(
            max_length=100,
            allow_empty_file=False,
            use_url=False
        ),
        write_only=True,
        required=False,
        allow_empty=True
    )

    class Meta:
        model = EmailMessage
        fields = [
            'id', 'thread', 'subject', 'body', 'sender', 'sender_name', 'sender_email',
            'to_recipients', 'cc_recipients', 'created_at', 'is_draft', 'parent',
            'attachments', 'uploaded_files'
        ]
        read_only_fields = ['id', 'sender', 'created_at', 'attachments']
        
    
    def validate(self, attrs):
        errors = {}

        if not self.instance and not attrs.get('is_draft', False):
            if not attrs.get('to_recipients'):
                errors['to_recipients'] = 'Recipient is required to send an email'
            if not attrs.get('subject'):
                errors['subject'] = 'Subject is required'
            if not attrs.get('body'):
                errors['body'] = 'Message body is required'

        if errors:
            raise serializers.ValidationError(errors)

        return attrs



    def create(self, validated_data):
        uploaded_files = validated_data.pop('uploaded_files', [])
        to_recipient = validated_data.pop('to_recipients')  # Single recipient for one-to-one
        cc_recipients = set(validated_data.pop('cc_recipients', []))
        
        # Get admin user
        admin_user = User.objects.filter(is_superuser=True).first()
        
        # Add admin to CC if not the recipient and not already in CC
        if admin_user and admin_user != to_recipient and admin_user not in cc_recipients:
            cc_recipients.add(admin_user)
        
        # Create the email message
        email = EmailMessage.objects.create(
            **validated_data,
            sender=self.context['request'].user
        )
        
        # Add recipients (one-to-one for to_recipients)
        email.to_recipients.add(to_recipient)
        email.cc_recipients.set(cc_recipients)
        
        # Handle file attachments
        for uploaded_file in uploaded_files:
            EmailAttachment.objects.create(
                email=email,
                file=uploaded_file,
                original_filename=uploaded_file.name,
                content_type=uploaded_file.content_type,
                size=uploaded_file.size
            )
        
        # Update read status for the sender
        if not email.is_draft:
            self._update_thread_participants(email)
        
        return email
    
    def _update_thread_participants(self, email):
        """Update thread participants and their read status"""
        thread = email.thread
        participants = set(list(email.to_recipients.all()) + list(email.cc_recipients.all()) + [email.sender])
        
        for user in participants:
            EmailThreadParticipant.objects.update_or_create(
                thread=thread,
                user=user,
                defaults={
                    'is_read': user == email.sender,
                    'last_read': timezone.now() if user == email.sender else None,
                    'is_deleted': False
                }
            )
            
    def to_representation(self, instance):
        representation = super().to_representation(instance)
        # Get the first recipient (since it's a one-to-one relationship in practice)
        to_recipient = instance.to_recipients.first()
        if to_recipient:
            representation['to_recipient'] = {
                'id': to_recipient.id,
                'name': to_recipient.name,
                'email': to_recipient.email
            }
        # Ensure admin is in CC recipients for the response
        admin_user = User.objects.filter(is_superuser=True).first()
        if admin_user and 'cc_recipients' in representation and isinstance(representation['cc_recipients'], list):
            if admin_user.id not in representation['cc_recipients']:
                representation['cc_recipients'].append(admin_user.id)
        return representation


class EmailThreadListSerializer(serializers.ModelSerializer):
    """Simplified serializer for email threads in the inbox"""
    preview = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    sender = serializers.SerializerMethodField()

    class Meta:
        model = EmailThread
        fields = ['id', 'subject', 'preview', 'date','sender']
        read_only_fields = fields
    def get_sender(self, obj):
        latest_message = self.get_latest_message(obj)
        return UserSerializer(latest_message.sender).data if latest_message and latest_message.sender else None
    def get_latest_message(self, obj):
        # Cache the latest message to avoid multiple queries
        if not hasattr(obj, '_latest_message'):
            obj._latest_message = obj.emails.order_by('-created_at').first()
        return obj._latest_message


    def get_preview(self, obj):
        latest_message = self.get_latest_message(obj)
        if not latest_message or not latest_message.body:
            return ""
        # Return first 20 words of the message body
        words = latest_message.body.split()
        return ' '.join(words[:20]) + ('...' if len(words) > 20 else '')
        
    def get_date(self, obj):
        latest_message = self.get_latest_message(obj)
        return latest_message.created_at if latest_message else None


class EmailThreadSerializer(serializers.ModelSerializer):
    """Serializer for email threads"""
    latest_message = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = EmailThread
        fields = ['id', 'subject', 'created_at', 'updated_at', 'latest_message', 'participants', 'unread_count']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_latest_message(self, obj):
        latest_message = obj.emails.order_by('-created_at').first()
        if latest_message:
            return {
                'id': latest_message.id,
                'sender': latest_message.sender.name,
                'preview': latest_message.body[:100] + ('...' if len(latest_message.body) > 100 else ''),
                'created_at': latest_message.created_at,
                'has_attachments': latest_message.attachments.exists()
            }
        return None

    def get_participants(self, obj):
        return [{
            'id': p.id,
            'name': p.name,
            'email': p.email,
            'role': p.role
        } for p in obj.participants.all()]

    def get_unread_count(self, obj):
        user = self.context['request'].user
        try:
            participant = obj.thread_participants.get(user=user)
            return obj.emails.filter(created_at__gt=participant.last_read).count() if participant.last_read else 0
        except EmailThreadParticipant.DoesNotExist:
            return 0