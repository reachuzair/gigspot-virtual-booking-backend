from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings

def send_templated_email(subject, recipient_list, template_name, context):
    """
    Send email using a template with HTML and plain text versions
    
    Args:
        subject: Email subject
        recipient_list: List of recipient emails
        template_name: Base name of the template (without extension)
        context: Dictionary with template variables
    """
    # Render HTML content
    html_content = render_to_string(f"emails/{template_name}.html", context)

    # Render plain text content by stripping HTML tags
    # text_content = render_to_string(f"emails/{template_name}.txt", context)
    
    # Create email
    email = EmailMultiAlternatives(
        subject=subject,
        body=html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipient_list,
    )
    email.attach_alternative(html_content, "text/html")
    email.send()