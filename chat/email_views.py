from rest_framework import status, permissions, generics
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from django.db.models import Q, F
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.http import Http404
from .models import EmailThread, EmailMessage, EmailThreadParticipant, EmailAttachment
from .serializers import (
    EmailThreadSerializer, EmailThreadListSerializer, 
    EmailMessageSerializer, EmailAttachmentSerializer
)
from django.contrib.auth import get_user_model
from rest_framework.pagination import PageNumberPagination
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class ReplyToEmailView(generics.CreateAPIView):
    """
    Reply to an email message
    """
    serializer_class = EmailMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def create(self, request, message_id):
        # Get the parent message
        parent_message = get_object_or_404(
            EmailMessage.objects.filter(
                Q(pk=message_id),
                Q(to_recipients=request.user) | 
                Q(cc_recipients=request.user) |
                Q(sender=request.user)
            ).distinct()
        )

        # Handle file uploads
        files = request.FILES.getlist('files[]', []) or request.FILES.getlist('files', [])
        if files:
            mutable_data = request.data.copy()
            mutable_data.setlist('uploaded_files', files)
            request._full_data = mutable_data

        # Set up the reply data
        reply_data = request.data.copy()
        reply_data['thread'] = parent_message.thread_id
        reply_data['parent'] = parent_message.id
        
        # Set default subject if not provided
        if 'subject' not in reply_data or not reply_data['subject']:
            if not parent_message.subject.startswith('Re: '):
                reply_data['subject'] = f"Re: {parent_message.subject}"
            else:
                reply_data['subject'] = parent_message.subject
        
        # Set the sender as the current user
        reply_data['sender'] = request.user.id
        
        # Set the recipient - default to original sender if not specified
        if 'to_recipients' not in reply_data or not reply_data['to_recipients']:
            # If no recipient specified, reply to the original sender
            reply_data['to_recipients'] = parent_message.sender_id
        
        # Let the serializer handle cc_recipients
        if 'cc_recipients' in reply_data:
            del reply_data['cc_recipients']
        
        # Quote the original message in the body
        if 'body' in reply_data and parent_message.body:
            quoted_body = f"\n\n\nOn {parent_message.created_at.strftime('%Y-%m-%d %H:%M')} {parent_message.sender.name} wrote:\n"
            quoted_body += "> " + "\n> ".join(parent_message.body.split('\n'))
            reply_data['body'] = f"{reply_data['body']}{quoted_body}"
        
        serializer = self.get_serializer(data=reply_data)
        serializer.is_valid(raise_exception=True)
        
        # Mark thread as updated
        if parent_message.thread:
            parent_message.thread.updated_at = timezone.now()
            parent_message.thread.save()
        
        self.perform_create(serializer)
        
        # Update thread participants
        email_message = serializer.instance
        if email_message.thread:
            participants = set(email_message.to_recipients.all()) | set(email_message.cc_recipients.all())
            participants.add(email_message.sender)
            
            for user in participants:
                EmailThreadParticipant.objects.get_or_create(
                    thread=email_message.thread,
                    user=user,
                    defaults={
                        'is_read': user == request.user,
                        'last_read': timezone.now() if user == request.user else None,
                        'is_deleted': False
                    }
                )
        
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class EmailInboxView(generics.ListAPIView):
    """
    List all email threads for the current user's inbox with simplified data
    """
    serializer_class = EmailThreadListSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        return EmailThread.objects.filter(
            thread_participants__user=user,
            thread_participants__is_deleted=False,
            emails__is_draft=False  # Exclude drafts from inbox
        ).annotate(
            latest_message_date=models.Max('emails__created_at')
        ).order_by('-latest_message_date').distinct()


class DraftEmailListView(generics.ListAPIView):
    """
    List all draft emails for the current user
    """
    serializer_class = EmailMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        return EmailMessage.objects.filter(
            sender=self.request.user,
            is_draft=True
        ).select_related('sender', 'thread').prefetch_related(
            'to_recipients', 'cc_recipients', 'attachments'
        ).order_by('-created_at')

class EmailThreadListCreateView(generics.ListCreateAPIView):
    """
    List all email threads for the current user or create a new email thread
    """
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user
        # Get threads where the user is a participant and not deleted
        return EmailThread.objects.filter(
            thread_participants__user=user,
            thread_participants__is_deleted=False
        ).distinct().order_by('-updated_at')

    def perform_create(self, serializer):
        serializer.save()


class EmailThreadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete an email thread
    """
    serializer_class = EmailThreadSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        user = self.request.user
        return EmailThread.objects.filter(
            thread_participants__user=user,
            thread_participants__is_deleted=False
        ).prefetch_related('thread_participants__user')

    def perform_destroy(self, instance):
        # Instead of deleting, mark as deleted for the current user
        EmailThreadParticipant.objects.filter(
            thread=instance,
            user=self.request.user
        ).update(is_deleted=True)


class EmailMessageListCreateView(generics.ListCreateAPIView):
    """
    List all messages in a thread or create a new message
    """
    serializer_class = EmailMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        thread_id = self.kwargs.get('thread_id')
        return EmailMessage.objects.filter(
            thread_id=thread_id,
            thread__thread_participants__user=self.request.user,
            thread__thread_participants__is_deleted=False
        ).select_related('sender', 'thread').prefetch_related(
            'to_recipients', 'cc_recipients', 'attachments'
        ).order_by('created_at')

    def get_serializer_context(self):
        return {'request': self.request}

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Get the thread and check permissions
        thread_id = kwargs.get('thread_id')
        thread = get_object_or_404(
            EmailThread.objects.filter(
                thread_participants__user=request.user,
                thread_participants__is_deleted=False
            ),
            pk=thread_id
        )

        # Add thread to the request data
        request.data['thread'] = thread.id
        
        # Ensure we're working with a single recipient
        if 'to_recipients' in request.data and isinstance(request.data['to_recipients'], list):
            request.data['to_recipients'] = request.data['to_recipients'][0] if request.data['to_recipients'] else None
        
        # Handle file uploads
        files = request.FILES.getlist('files', [])
        if files:
            request.data['uploaded_files'] = files
            
        # Get admin user to add to CC if not already present
        admin_user = User.objects.filter(is_superuser=True).first()
        if admin_user and 'cc_recipients' not in request.data:
            request.data['cc_recipients'] = [admin_user.id]

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Mark thread as updated
        thread.updated_at = timezone.now()
        thread.save(update_fields=['updated_at'])
        
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)


class ComposeEmailView(generics.CreateAPIView):
    """
    Compose a new email with options to save as draft or send immediately
    """
    serializer_class = EmailMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_serializer_context(self):
        return {'request': self.request}

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Make a mutable copy of request.data
        mutable_data = request.data.copy()

        # Handle file uploads - support both 'files[]' and 'files'
        files = request.FILES.getlist('files[]', []) or request.FILES.getlist('files', [])
        if files:
            mutable_data.setlist('uploaded_files', files)

        # Determine if it's a draft
        is_draft = mutable_data.get('is_draft', 'false').lower() == 'true'

        # For drafts, we don’t require a recipient
        if not is_draft and not mutable_data.get('to_recipients'):
            return Response(
                {'detail': 'Recipient is required to send an email'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not is_draft and not mutable_data.get('subject'):
            return Response(
                {'detail': 'subject is required to send an email'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not is_draft and not mutable_data.get('body'):
            return Response(
                {'detail': 'body is required to send an email'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if this is a reply
        parent_id = mutable_data.get('parent_id')
        thread = None
        if parent_id:
            parent = get_object_or_404(
                EmailMessage.objects.filter(
                    thread__thread_participants__user=request.user
                ),
                pk=parent_id
            )
            mutable_data['thread'] = parent.thread_id
            mutable_data['parent'] = parent_id
            thread = parent.thread
        else:
            # Create a new thread for non-drafts or drafts with a subject
            if not is_draft or mutable_data.get('subject'):
                thread = EmailThread.objects.create(
                    subject=mutable_data.get('subject', 'No Subject')
                )
                mutable_data['thread'] = thread.id
            else:
                return Response(
                    {'detail': 'Subject is required for drafts'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Normalize recipient fields
        to_recipients = request.data.getlist('to_recipients')
        if to_recipients:
            mutable_data.setlist('to_recipients', to_recipients)

        # Handle cc_recipients
        cc_recipients = request.data.getlist('cc_recipients')
        cc_ids = []
        for val in cc_recipients:
            try:
                cc_ids.append(int(val))
            except (TypeError, ValueError):
                continue

        # Add admin to CC if sending
        if not is_draft:
            admin_user = User.objects.filter(is_superuser=True).first()
            if admin_user and admin_user.id not in cc_ids:
                cc_ids.append(admin_user.id)

        mutable_data.setlist('cc_recipients', [str(uid) for uid in cc_ids])

        # Set is_draft flag properly
        mutable_data['is_draft'] = str(is_draft).lower()

        # Serialize and save
        serializer = self.get_serializer(data=mutable_data)
        serializer.is_valid(raise_exception=True)
        email_message = serializer.save()

        # Update thread
        if thread:
            thread.updated_at = timezone.now()
            thread.save(update_fields=['updated_at'])

            # Add participants if sent
            if not is_draft:
                participants = {request.user}
                if email_message.to_recipients.exists():
                    participants.update(email_message.to_recipients.all())
                if email_message.cc_recipients.exists():
                    participants.update(email_message.cc_recipients.all())

                for user in participants:
                    EmailThreadParticipant.objects.get_or_create(
                        thread=thread,
                        user=user,
                        defaults={
                            'is_read': user == request.user,
                            'last_read': timezone.now() if user == request.user else None
                        }
                    )

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)



class EmailMessageDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete an email message
    """
    serializer_class = EmailMessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = 'pk'

    def get_queryset(self):
        return EmailMessage.objects.filter(
            Q(sender=self.request.user) | 
            Q(to_recipients=self.request.user) |
            Q(cc_recipients=self.request.user)
        ).distinct()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Mark as read if the user is a recipient
        if request.user != instance.sender:
            EmailThreadParticipant.objects.filter(
                thread=instance.thread,
                user=request.user
            ).update(
                is_read=True,
                last_read=timezone.now()
            )
            
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class MarkThreadAsReadView(APIView):
    """
    Mark all messages in a thread as read for the current user
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, thread_id):
        updated = EmailThreadParticipant.objects.filter(
            thread_id=thread_id,
            user=request.user
        ).update(
            is_read=True,
            last_read=timezone.now()
        )
        
        if updated:
            return Response({"status": "marked as read"}, status=status.HTTP_200_OK)
        return Response({"error": "Thread not found"}, status=status.HTTP_404_NOT_FOUND)
class SendDraftView(APIView):
    """
    Send a draft email
    """
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return EmailMessage.objects.filter(
            sender=self.request.user,
            is_draft=True
        )
        
    def get_object(self, pk):
        try:
            return self.get_queryset().get(pk=pk)
        except EmailMessage.DoesNotExist:
            raise Http404
            
    def post(self, request, pk, format=None):
        return self.send_draft(request, pk)
        
    def patch(self, request, pk, format=None):
        return self.send_draft(request, pk)

    @transaction.atomic
    def send_draft(self, request, pk):
        instance = self.get_object(pk)
        
        # Validate required fields
        if not instance.to_recipients.exists():
            return Response(
                {'detail': 'Recipient is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        if not instance.subject:
            return Response(
                {'error': 'Subject is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        if not instance.body:
            return Response(
                {'error': 'Message body is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Convert draft to sent email
        instance.is_draft = False
        instance.save()
        
        # Update thread's updated_at
        if instance.thread:
            instance.thread.updated_at = timezone.now()
            instance.thread.save()
        
        # Ensure all participants are in the thread
        if instance.thread:
            participants = set(instance.to_recipients.all()) | set(instance.cc_recipients.all())
            participants.add(instance.sender)
            
            # Add admin user to CC if not already present
            admin_user = User.objects.filter(is_superuser=True).first()
            if admin_user:
                participants.add(admin_user)
            
            for user in participants:
                EmailThreadParticipant.objects.get_or_create(
                    thread=instance.thread,
                    user=user,
                    defaults={
                        'is_read': user == request.user,
                        'last_read': timezone.now() if user == request.user else None
                    }
                )

        # Send email notification asynchronously
        # from django_rq import enqueue
        # enqueue(send_email_notification, instance)
        
        # Serialize the response
        serializer = EmailMessageSerializer(instance, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        instance = self.get_object(kwargs['pk'])
        
        # Validate required fields
        if not instance.to_recipients.exists():
            return Response(
                {'detail': 'Recipient is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        if not instance.subject:
            return Response(
                {'detail': 'Subject is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        if not instance.body:
            return Response(
                {'detail': 'Message body is required to send an email'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update the instance
        instance.is_draft = False
        instance.save(update_fields=['is_draft', 'updated_at'])

        # Add admin to CC if not already present
        admin_user = User.objects.filter(is_superuser=True).first()
        if admin_user and not instance.cc_recipients.filter(id=admin_user.id).exists():
            instance.cc_recipients.add(admin_user)

        # Update thread
        if instance.thread:
            instance.thread.updated_at = timezone.now()
            instance.thread.save(update_fields=['updated_at'])

            # Add all participants to the thread
            participants = {request.user}
            if instance.to_recipients.exists():
                participants.add(instance.to_recipients.first())
            if admin_user:
                participants.add(admin_user)
            
            for user in participants:
                EmailThreadParticipant.objects.get_or_create(
                    thread=instance.thread,
                    user=user,
                    defaults={
                        'is_read': user == request.user,
                        'last_read': timezone.now() if user == request.user else None
                    }
                )

        # Send email notification asynchronously
        # from django_rq import enqueue
        # enqueue(send_email_notification, instance)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

class EmailAttachmentDownloadView(generics.RetrieveAPIView):
    """
    Download an email attachment
    """
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        return EmailAttachment.objects.filter(
            email__thread__thread_participants__user=self.request.user
        )
    
    def retrieve(self, request, *args, **kwargs):
        attachment = self.get_object()
        response = FileResponse(attachment.file)
        response['Content-Disposition'] = f'attachment; filename="{attachment.original_filename}"'
        return response
