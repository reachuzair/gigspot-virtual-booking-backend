from custom_auth.models import ROLE_CHOICES, Artist, Venue, Fan
from django.conf import settings
import stripe
import time
import logging

logger = logging.getLogger(__name__)
stripe.api_key = settings.STRIPE_SECRET_KEY


def create_stripe_account(request, user, max_retries=3):
    """
    Create a new Stripe Connect account for the user and save the account ID to their profile.
    
    Args:
        request: The HTTP request object
        user: The user to create the Stripe account for
        max_retries: Maximum number of retry attempts
        
    Returns:
        dict: Contains 'stripe_account' and 'link' on success, None on failure
    """
    from django.db import transaction
    
    for attempt in range(max_retries):
        try:
            # 1. Collect ALL required fields upfront
            account_data = {
                "type": "express",
                "country": "US",  # Required
                "email": user.email,  # Required
                "business_type": "individual",  # Required for most cases
                "individual": {
                    "first_name": user.name.split(" ")[0] if user.name else "",  # Highly recommended
                    "last_name": user.name.split(" ")[1] if user.name and len(user.name.split(" ")) > 1 else "",
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
            logger.info(f"Created Stripe account {account.id} for user {user.id}")
            
            # 3. Save Stripe account ID to user's profile (artist or venue)
            try:
                with transaction.atomic():
                    if hasattr(user, 'artist'):
                        user.artist.stripe_account_id = account.id
                        user.artist.save(update_fields=['stripe_account_id', 'updated_at'])
                        logger.info(f"Saved Stripe account ID to artist profile {user.artist.id}")
                    elif hasattr(user, 'venue'):
                        user.venue.stripe_account_id = account.id
                        user.venue.save(update_fields=['stripe_account_id', 'updated_at'])
                        logger.info(f"Saved Stripe account ID to venue profile {user.venue.id}")
                    else:
                        logger.warning(f"User {user.id} has neither artist nor venue profile")
                        # Still proceed with account creation, but log the warning
            except Exception as e:
                logger.error(f"Error saving Stripe account ID to profile: {str(e)}")
                # Don't fail the whole process if we can't save to profile
                # The webhook will try to update this later
            
            # 4. Create onboarding link
            link = stripe.AccountLink.create(
                account=account.id,
                refresh_url=f"https://www.gigspotvb.com/",
                return_url=f"https://www.gigspotvb.com/",
                type="account_onboarding"
            )
            
            return {
                "stripe_account": account,
                "link": link
            }
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe error (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt == max_retries - 1:
                logger.error(f"Stripe account creation failed after {max_retries} attempts: {str(e)}")
                return None
            time.sleep(1)  # Wait before retrying


import qrcode
from io import BytesIO
import logging
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

def create_qr_code(booking_code):
    """
    Generates a QR code image containing the booking_code and returns it as a Django ContentFile.
    """
    try:
        logger.info(f"Generating QR code for booking: {booking_code}")
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
        buffer.seek(0)  # Rewind the buffer to the beginning
        
        file_name = f"qr_{booking_code}.png"
        content_file = ContentFile(buffer.getvalue(), name=file_name)
        
        logger.info(f"Successfully generated QR code: {file_name}")
        return content_file
        
    except Exception as e:
        logger.error(f"Error generating QR code for {booking_code}: {str(e)}")
        raise
    