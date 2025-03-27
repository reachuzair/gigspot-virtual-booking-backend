from django.core.mail import send_mail
from dotenv import load_dotenv
import os

load_dotenv()

def send_notify_email(email, subject, message):
    from_email = os.getenv('EMAIL_HOST_USER')  # Replace with your sender email
    recipient_list = [email]
    send_mail(subject, message, from_email, recipient_list)