from django.urls import path
from . import email_views

app_name = 'email_api'

urlpatterns = [
    path('inbox/', email_views.EmailInboxView.as_view(), name='inbox'),
    path('threads/', email_views.EmailThreadListCreateView.as_view(), name='thread-list'),
    path('threads/<int:pk>/', email_views.EmailThreadDetailView.as_view(), name='thread-detail'),
    
    path('threads/<int:thread_id>/messages/', email_views.EmailMessageListCreateView.as_view(), name='message-list'),
    path('messages/<int:pk>/', email_views.EmailMessageDetailView.as_view(), name='message-detail'),
    path('messages/<int:message_id>/reply/', email_views.ReplyToEmailView.as_view(), name='reply-to-email'),
    path('threads/<int:thread_id>/mark-read/', email_views.MarkThreadAsReadView.as_view(), name='mark-thread-read'),
    
    path('drafts/<int:pk>/send/', email_views.SendDraftView.as_view(), name='send-draft'),
    path('compose/', email_views.ComposeEmailView.as_view(), name='compose-email'),
    path('drafts/', email_views.DraftEmailListView.as_view(), name='draft-list'),
    
    path('attachments/<int:pk>/', email_views.EmailAttachmentDownloadView.as_view(), name='download-attachment'),
]
