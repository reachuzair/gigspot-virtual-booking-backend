from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.validators import FileExtensionValidator
import uuid
import os

def email_attachment_path(instance, filename):
    # File will be uploaded to MEDIA_ROOT/email_attachments/<email_id>/<filename>
    return f'email_attachments/{instance.email.id}/{filename}'

class ChatRoom(models.Model):
    ROOM_TYPE_CHOICES = (
        ('private', 'Private'),
        ('group', 'Group'),
    )

    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES)
    name = models.CharField(max_length=255, blank=True, null=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    # gig = models.ForeignKey('gig.Gig', on_delete=models.CASCADE, null=True, blank=True, related_name='chat_rooms')
    updated_at = models.DateTimeField(auto_now=True)
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='chat_rooms')

    def __str__(self):
        return self.name if self.room_type == 'group' else f'Chat {self.id}'


class Message(models.Model):
    chat_room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    content = models.JSONField(default=dict) 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False) 

    def __str__(self):
        return f'Message {self.id} in Room {self.chat_room.id}'
    
class MessageReadStatus(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='read_statuses')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('message', 'user')


class EmailThread(models.Model):
    """
    A thread that groups related email messages together
    """
    subject = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='email_threads',
        through='EmailThreadParticipant'
    )

    def __str__(self):
        return f"Email Thread: {self.subject}"


class EmailThreadParticipant(models.Model):
    """
    Tracks participants in an email thread and their read status
    """
    thread = models.ForeignKey(EmailThread, on_delete=models.CASCADE, related_name='thread_participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_thread_participation')
    is_read = models.BooleanField(default=False)
    last_read = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        unique_together = ('thread', 'user')


class EmailMessage(models.Model):
    """
    Represents an email message within a thread
    """
    thread = models.ForeignKey(
        EmailThread,
        on_delete=models.CASCADE,
        related_name='emails',
        null=True,
        blank=True
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_emails'
    )
    to_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='received_emails',
        blank=True
    )
    cc_recipients = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='cc_emails',
        blank=True
    )
    subject = models.CharField(max_length=255)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_draft = models.BooleanField(default=False)
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='replies'
    )

    def __str__(self):
        return f"{self.subject} - {self.sender}"


class EmailAttachment(models.Model):
    """
    Represents a file attached to an email
    """
    email = models.ForeignKey(
        EmailMessage,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(
        upload_to=email_attachment_path,
        validators=[
            FileExtensionValidator(
                allowed_extensions=['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'gif', 'txt']
            )
        ]
    )
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.original_filename and hasattr(self.file, 'name'):
            self.original_filename = os.path.basename(self.file.name)
        if not self.size and hasattr(self.file, 'size'):
            self.size = self.file.size
        super().save(*args, **kwargs)

    def __str__(self):
        return self.original_filename

