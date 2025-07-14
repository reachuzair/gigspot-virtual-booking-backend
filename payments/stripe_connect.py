import stripe
import logging
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings

logger = logging.getLogger(__name__)

class StripeConnectView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get_stripe_account_id(self, user):
        """Get Stripe account ID from user's artist or venue profile."""
        logger.info(f"[Stripe] Looking up Stripe account for user {user.id} ({user.email})")
        
        # Check artist profile first
        if hasattr(user, 'artist_profile'):
            artist = user.artist_profile
            logger.info(f"[Stripe] User has artist profile: {artist.id}")
            
            # Check if artist has stripe_account_id attribute
            if not hasattr(artist, 'stripe_account_id'):
                logger.warning(f"[Stripe] Artist profile {artist.id} has no stripe_account_id attribute")
                return None
                
            logger.info(f"[Stripe] Artist {artist.id} has stripe_account_id: {artist.stripe_account_id}")
            
            if not artist.stripe_account_id:
                logger.warning(f"[Stripe] Artist {artist.id} has empty stripe_account_id")
                return None
                
            logger.info(f"[Stripe] Using artist's Stripe account ID: {artist.stripe_account_id}")
            return artist.stripe_account_id
        
        logger.info(f"[Stripe] User {user.id} has no artist profile")
            
        # If no artist account, check venue profile
        if hasattr(user, 'venue_profile'):
            venue = user.venue_profile
            logger.info(f"[Stripe] User has venue profile: {venue.id}")
            
            # Check if venue has stripe_account_id attribute
            if not hasattr(venue, 'stripe_account_id'):
                logger.warning(f"[Stripe] Venue profile {venue.id} has no stripe_account_id attribute")
                return None
                
            logger.info(f"[Stripe] Venue {venue.id} has stripe_account_id: {venue.stripe_account_id}")
            
            if not venue.stripe_account_id:
                logger.warning(f"[Stripe] Venue {venue.id} has empty stripe_account_id")
                return None
                
            logger.info(f"[Stripe] Using venue's Stripe account ID: {venue.stripe_account_id}")
            return venue.stripe_account_id
        
        logger.warning(f"[Stripe] User {user.id} has neither artist nor venue profile")
        return None
    
    def get_onboarding_link(self, stripe_account_id):
        """Generate or retrieve account onboarding link."""
        try:
            account_links = stripe.AccountLink.create(
                account=stripe_account_id,
                refresh_url=f"{settings.FRONTEND_URL}/dashboard/payments?tab=withdrawals",
                return_url=f"{settings.FRONTEND_URL}/dashboard/payments?tab=withdrawals",
                type='account_onboarding',
            )
            return account_links.url
        except stripe.error.StripeError as e:
            logger.error(f"Error creating onboarding link: {str(e)}")
            return None

class AccountBalanceView(StripeConnectView):
    def get(self, request):
        """Get current account balance."""
        stripe_account_id = self.get_stripe_account_id(request.user)
        if not stripe_account_id:
            return Response(
                {'detail': 'Stripe account not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            balance = stripe.Balance.retrieve(stripe_account=stripe_account_id)
            return Response({
                'available': [{'amount': b.amount, 'currency': b.currency.upper()} for b in balance.available],
                'pending': [{'amount': b.amount, 'currency': b.currency.upper()} for b in balance.pending],
            })
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching balance: {str(e)}")
            return Response(
                {'detail': 'Error fetching account balance'},
                status=status.HTTP_400_BAD_REQUEST
            )

class TransactionHistoryView(StripeConnectView):
    def get(self, request):
        """Get transaction history."""
        logger.info(f"[TransactionHistory] Fetching transaction history for user: {request.user.id} ({request.user.email})")
        
        # Log user attributes for debugging
        logger.info(f"[TransactionHistory] User attributes: {dir(request.user)}")
        
        # Check if user has artist or venue profile
        if hasattr(request.user, 'artist'):
            logger.info(f"[TransactionHistory] User has artist profile: {request.user.artist.id}")
            logger.info(f"[TransactionHistory] Artist stripe_account_id: {getattr(request.user.artist, 'stripe_account_id', 'Not set')}")
        elif hasattr(request.user, 'venue'):
            logger.info(f"[TransactionHistory] User has venue profile: {request.user.venue.id}")
            logger.info(f"[TransactionHistory] Venue stripe_account_id: {getattr(request.user.venue, 'stripe_account_id', 'Not set')}")
        else:
            logger.warning("[TransactionHistory] User has neither artist nor venue profile")
        
        # Get Stripe account ID
        stripe_account_id = self.get_stripe_account_id(request.user)
        logger.info(f"[TransactionHistory] Retrieved stripe_account_id: {stripe_account_id}")
        
        if not stripe_account_id:
            logger.warning(f"[TransactionHistory] No Stripe account found for user {request.user.id}")
            return Response(
                {'detail': 'Stripe account not found. Please complete the Stripe Connect onboarding process.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Get last 30 days of transactions
            start_date = int((datetime.now() - timedelta(days=30)).timestamp())
            
            transactions = stripe.BalanceTransaction.list(
                stripe_account=stripe_account_id,
                created={'gte': start_date},
                limit=50
            )
            
            return Response([{
                'id': txn.id,
                'amount': txn.amount,
                'currency': txn.currency.upper(),
                'type': txn.type,
                'status': txn.status,
                'created': txn.created,
                'available_on': txn.available_on,
                'fee': txn.fee,
                'net': txn.net,
                'description': txn.description,
            } for txn in transactions.data])
            
        except stripe.error.StripeError as e:
            logger.error(f"Error fetching transactions: {str(e)}")
            return Response(
                {'detail': 'Error fetching transaction history'},
                status=status.HTTP_400_BAD_REQUEST
            )

class PayoutView(StripeConnectView):
    def post(self, request):
        """Initiate a payout to connected account's bank."""
        amount = request.data.get('amount')
        currency = request.data.get('currency', 'usd').lower()
        
        if not amount or amount <= 0:
            return Response(
                {'detail': 'Invalid amount'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        stripe_account_id = self.get_stripe_account_id(request.user)
        if not stripe_account_id:
            return Response(
                {'detail': 'Stripe account not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            # Check if account is fully onboarded
            account = stripe.Account.retrieve(stripe_account_id)
            if not account.details_submitted:
                onboarding_link = self.get_onboarding_link(stripe_account_id)
                return Response(
                    {
                        'detail': 'Account setup not completed',
                        'onboarding_required': True,
                        'onboarding_url': onboarding_link
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED
                )
            
            # Create payout
            payout = stripe.Payout.create(
                amount=int(amount * 100),  # Convert to cents
                currency=currency,
                stripe_account=stripe_account_id
            )
            
            # Save payout record
            from .models import Payout, BankAccount
            # Get the default bank account for the user
            bank_account = BankAccount.objects.filter(
                user=request.user,
                is_default=True
            ).first()
            
            Payout.objects.create(
                user=request.user,
                bank_account=bank_account,
                amount=amount,
                status=payout.status,
                stripe_payout_id=payout.id,
                fee=0  # You might want to calculate this from the payout object if available
            )
            
            return Response({
                'id': payout.id,
                'amount': payout.amount / 100,  # Convert back to dollars
                'currency': payout.currency.upper(),
                'status': payout.status,
                'arrival_date': payout.arrival_date,
                'destination': payout.destination
            })
            
        except stripe.error.StripeError as e:
            logger.error(f"Error creating payout: {str(e)}")
            return Response(
                {'detail': str(e.user_message) if hasattr(e, 'user_message') else 'Error processing payout'},
                status=status.HTTP_400_BAD_REQUEST
            )

class OnboardingStatusView(StripeConnectView):
    def get(self, request):
        """Get account onboarding status and link if needed."""
        logger.info(f"[OnboardingStatus] Getting status for user: {request.user.id} ({request.user.email})")
        
        # Log user attributes for debugging
        logger.info(f"[OnboardingStatus] User attributes: {dir(request.user)}")
        
        # Check if user has artist or venue profile
        if hasattr(request.user, 'artist'):
            logger.info(f"[OnboardingStatus] User has artist profile: {request.user.artist.id}")
            logger.info(f"[OnboardingStatus] Artist stripe_account_id: {getattr(request.user.artist, 'stripe_account_id', 'Not set')}")
            logger.info(f"[OnboardingStatus] Artist stripe_onboarding_completed: {getattr(request.user.artist, 'stripe_onboarding_completed', 'Not set')}")
        elif hasattr(request.user, 'venue'):
            logger.info(f"[OnboardingStatus] User has venue profile: {request.user.venue.id}")
            logger.info(f"[OnboardingStatus] Venue stripe_account_id: {getattr(request.user.venue, 'stripe_account_id', 'Not set')}")
            logger.info(f"[OnboardingStatus] Venue stripe_onboarding_completed: {getattr(request.user.venue, 'stripe_onboarding_completed', 'Not set')}")
        else:
            logger.warning("[OnboardingStatus] User has neither artist nor venue profile")
        
        # Get Stripe account ID
        stripe_account_id = self.get_stripe_account_id(request.user)
        logger.info(f"[OnboardingStatus] Retrieved stripe_account_id: {stripe_account_id}")
        
        if not stripe_account_id:
            logger.warning(f"[OnboardingStatus] No Stripe account found for user {request.user.id}")
            return Response(
                {'detail': 'Stripe account not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            logger.info(f"[OnboardingStatus] Retrieving Stripe account: {stripe_account_id}")
            account = stripe.Account.retrieve(stripe_account_id)
            
            logger.info(f"[OnboardingStatus] Stripe account details: {account}")
            
            response_data = {
                'details_submitted': account.details_submitted,
                'payouts_enabled': account.payouts_enabled,
                'charges_enabled': account.charges_enabled,
                'requirements': getattr(account, 'requirements', None),
            }
            
            logger.info(f"[OnboardingStatus] Account status - Details submitted: {account.details_submitted}, "
                      f"Payouts enabled: {account.payouts_enabled}, Charges enabled: {account.charges_enabled}")
            
            if not account.details_submitted:
                onboarding_link = self.get_onboarding_link(stripe_account_id)
                response_data['onboarding_url'] = onboarding_link
                
            return Response(response_data)
            
        except stripe.error.StripeError as e:
            logger.error(f"Error checking onboarding status: {str(e)}")
            return Response(
                {'detail': 'Error checking account status'},
                status=status.HTTP_400_BAD_REQUEST
            )
