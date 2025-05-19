from custom_auth.models import Artist, Fan
from gigs.models import Gig
from .models import Payment, Ticket, PaymentStatus
from carts.models import CartItem
from gigs.models import Contract
from django.utils import timezone

def handle_account_update(account):
    artist = Artist.objects.get(stripe_account_id=account.id)

    if account['charges_enabled'] and account['payouts_enabled']:
        artist.stripe_onboarding_completed = True
        artist.save()

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
            qr_code_image = create_qr_code(booking_code)
            Ticket.objects.create(
                booking_code=booking_code,
                user=fan,
                gig=gig,
                qr_code=qr_code_image,
                price=price_per_ticket
            )
        
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
            
            
                
            
