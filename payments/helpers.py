import os
import logging
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from custom_auth.models import Artist, Fan, Venue
from gigs.models import Gig, Contract
from .models import Payment, Ticket, PaymentStatus
from carts.models import CartItem

# Set up logging
logger = logging.getLogger(__name__)

def handle_account_update(account):
    """
    Handle Stripe Connect account update events.
    
    Args:
        account: The Stripe account object from the webhook event
    """
    from custom_auth.models import Artist, Venue
    import logging
    from django.db import transaction
    
    logger = logging.getLogger(__name__)
    account_id = account.get('id')
    
    if not account_id:
        logger.error("[Stripe Webhook] No account ID in account update event")
        return
        
    logger.info(f"[Stripe Webhook] Handling account update for Stripe account: {account_id}")
    logger.info(f"[Stripe Webhook] Account status - charges_enabled: {account.get('charges_enabled')}, "
               f"payouts_enabled: {account.get('payouts_enabled')}, "
               f"details_submitted: {account.get('details_submitted')}")
    
    try:
        # Try to find an artist with this Stripe account ID
        try:
            with transaction.atomic():
                artist = Artist.objects.select_for_update().get(stripe_account_id=account_id)
                logger.info(f"[Stripe Webhook] Found artist {artist.id} with Stripe account {account_id}")
                
                # Update onboarding status if needed
                charges_enabled = account.get('charges_enabled', False)
                payouts_enabled = account.get('payouts_enabled', False)
                
                if charges_enabled and payouts_enabled:
                    if not artist.stripe_onboarding_completed:
                        artist.stripe_onboarding_completed = True
                        artist.save(update_fields=['stripe_onboarding_completed', 'updated_at'])
                        logger.info(f"[Stripe Webhook] Marked artist {artist.id} as completed Stripe onboarding")
                    else:
                        logger.info(f"[Stripe Webhook] Artist {artist.id} already marked as completed onboarding")
                else:
                    logger.info(f"[Stripe Webhook] Account not fully enabled - charges: {charges_enabled}, payouts: {payouts_enabled}")
                
                return
                
        except Artist.DoesNotExist:
            logger.info(f"[Stripe Webhook] No artist found with Stripe account ID: {account_id}")
            pass
            
        # Try to find a venue with this Stripe account ID
        try:
            with transaction.atomic():
                venue = Venue.objects.select_for_update().get(stripe_account_id=account_id)
                logger.info(f"[Stripe Webhook] Found venue {venue.id} with Stripe account {account_id}")
                
                # Update onboarding status if needed
                charges_enabled = account.get('charges_enabled', False)
                payouts_enabled = account.get('payouts_enabled', False)
                
                if charges_enabled and payouts_enabled:
                    if not venue.stripe_onboarding_completed:
                        venue.stripe_onboarding_completed = True
                        venue.save(update_fields=['stripe_onboarding_completed', 'updated_at'])
                        logger.info(f"[Stripe Webhook] Marked venue {venue.id} as completed Stripe onboarding")
                    else:
                        logger.info(f"[Stripe Webhook] Venue {venue.id} already marked as completed onboarding")
                else:
                    logger.info(f"[Stripe Webhook] Account not fully enabled - charges: {charges_enabled}, payouts: {payouts_enabled}")
                
                return
                
        except Venue.DoesNotExist:
            logger.info(f"[Stripe Webhook] No venue found with Stripe account ID: {account_id}")
            pass
            
        logger.warning(f"[Stripe Webhook] No artist or venue found with Stripe account ID: {account_id}")
        
    except Exception as e:
        logger.error(f"[Stripe Webhook] Error handling account update for {account_id}: {str(e)}", exc_info=True)
        raise

import uuid
from payments.utils import create_qr_code

def handle_payment_intent_succeeded(payment_intent):
    metadata = payment_intent['metadata']
    payment_intent_for = metadata['payment_intent_for']
    
    if payment_intent_for == "ticket_purchase":
        gig_id = metadata['gig_id']
        fan_id = metadata['fan_id']
        item_id = metadata['item_id']
        quantity = int(metadata['quantity'])
        supporting_artist_id = metadata['supporting_artist_id']
        gig = Gig.objects.get(id=gig_id)
        fan = Fan.objects.get(id=fan_id)
        artist = Artist.objects.get(id=supporting_artist_id)
        cart_item = CartItem.objects.get(id=item_id)
        cart_item.is_booked = True
        cart_item.save()        
        # Calculate per-ticket price
        total_amount = payment_intent['amount']
        price_per_ticket = total_amount / int(quantity) / 100  # Convert cents to dollars

        # Create tickets
        for _ in range(int(quantity)):
            booking_code = str(uuid.uuid4())
            try:
                logger.info(f'Creating ticket with booking code: {booking_code}')
                
                # Create and save the ticket first
                ticket = Ticket(
                    booking_code=booking_code,
                    user=fan,
                    gig=gig,
                    price=price_per_ticket
                )
                ticket.save()  # Save the ticket first to get an ID
                
                logger.info(f'Ticket created with ID: {ticket.id}')
                
                try:
                    # Generate QR code
                    logger.info('Generating QR code...')
                    qr_code_image = create_qr_code(booking_code)
                    
                    # Save QR code to the ticket
                    qr_filename = f'qr_{ticket.id}_{booking_code}.png'
                    logger.info(f'Saving QR code as: {qr_filename}')
                    
                    # Ensure the media directory exists
                    qr_dir = os.path.join(settings.MEDIA_ROOT, 'tickets', 'qr_codes')
                    os.makedirs(qr_dir, exist_ok=True)
                    
                    # Save the QR code
                    ticket.qr_code.save(qr_filename, qr_code_image, save=True)
                    logger.info(f'Successfully saved QR code for ticket {ticket.id} at {ticket.qr_code.path}')
                    
                except Exception as qr_error:
                    logger.error(f'Error generating/saving QR code for ticket {ticket.id}: {str(qr_error)}')
                    # Don't fail the whole process if QR code generation fails
                    # The ticket will still be created but without a QR code
                    pass
                
            except Exception as e:
                logger.error(f'Error creating ticket: {str(e)}', exc_info=True)
                # Continue with other tickets if one fails
                continue
        
        # Record transaction
        Payment.objects.create(
            user=fan,
            payee=artist,
            amount=payment_intent['amount'] - payment_intent['application_fee_amount'],
            fee=payment_intent['application_fee_amount'],
            payment_intent_id=payment_intent['id'],
            status=PaymentStatus.COMPLETED
        )
    
    elif payment_intent_for == "contract_signature":
        contract_id = metadata['contract_id']
        contract = Contract.objects.get(id=contract_id)
        contract.is_paid = True
        contract.save()
        
        if metadata['is_host'] == 'true':
            contract.artist_signed = True
            contract.artist_signed_at = timezone.now()
            contract.save()
        else:
            gig = contract.gig
            artist = contract.artist
            if artist.id in gig.invitees.values_list('id', flat=True):
                contract.artist_signed = True
                contract.artist_signed_at = timezone.now()
                contract.save()
                gig.invitees.remove(artist)
                gig.collaborators.add(artist)
                gig.save()
            else:
                contract.collaborator_signed = True
                contract.collaborator_signed_at = timezone.now()
                contract.save()
                gig.collaborators.add(artist)
                gig.save()
            
            
                
            
