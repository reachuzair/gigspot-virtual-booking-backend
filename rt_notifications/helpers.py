from dotenv import load_dotenv
from utils.email import send_templated_email
import os

load_dotenv()

def send_notify_templated_email(email, notification_type, message, description):
    recipient_list = [email]
    if notification_type == 'message':
        send_templated_email(message, recipient_list, 'notification_message', {'message': message, 'description': description})
    elif notification_type == 'booking':
        send_templated_email(message, recipient_list, 'notification_booking', {'message': message, 'description': description})
    elif notification_type == 'system':
        send_templated_email(message, recipient_list, 'notification_system', {'message': message, 'description': description})