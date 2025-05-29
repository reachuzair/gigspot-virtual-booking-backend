from custom_auth.models import ROLE_CHOICES, Artist, Venue, Fan
from django.conf import settings
import stripe
import time
import logging

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_account(request, user, max_retries=3):
    for attempt in range(max_retries):
        try:
            # 1. Collect ALL required fields upfront
            account_data = {
                "type": "express",
                "country": "US",  # Required
                "email": user.email,  # Required
                "business_type": "individual",  # Required for most cases
                "individual": {
                    "first_name": user.name.split(" ")[0],  # Highly recommended
                    "last_name": user.name.split(" ")[1] if len(user.name.split(" ")) > 1 else "",
                    "email": user.email,
                },
                "business_profile": {
                    "url": "https://gigspotvb.com",  # Recommended
                    "mcc": "5734",  # Merchant Category Code (e.g., 5734 for Music)
                },
                "capabilities": {
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                "metadata": {"platform_user_id": user.id},
            }

            # 2. Create the Stripe account
            account = stripe.Account.create(**account_data)
            
            link = stripe.AccountLink.create(
                account=account.id,
                refresh_url=f"{settings.FRONTEND_URL}/onboarding/retry",
                return_url=f"{settings.FRONTEND_URL}/onboarding/success",
                type="account_onboarding"
            )
            
            return {
                "stripe_account": account,
                "link": link
            }
            
        except stripe.error.StripeError as e:
            if attempt == max_retries - 1:
                logger.error(f"Stripe account creation failed after {max_retries} attempts: {str(e)}")
                return None
            time.sleep(1)  # Wait before retrying
        


import qrcode
from io import BytesIO
from django.core.files.base import ContentFile


def create_qr_code(booking_code):
    """
    Generates a QR code image containing the booking_code and returns it as a Django ContentFile.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(booking_code)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    file_name = f"qr_{booking_code}.png"
    return ContentFile(buffer.getvalue(), name=file_name)
    