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
        """Get Stripe account ID from user's artist profile or settings."""
        if hasattr(user, 'artist') and hasattr(user.artist, 'stripe_account_id'):
            return user.artist.stripe_account_id
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
        stripe_account_id = self.get_stripe_account_id(request.user)
        if not stripe_account_id:
            return Response(
                {'detail': 'Stripe account not found'},
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
        stripe_account_id = self.get_stripe_account_id(request.user)
        if not stripe_account_id:
            return Response(
                {'detail': 'Stripe account not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            account = stripe.Account.retrieve(stripe_account_id)
            response_data = {
                'details_submitted': account.details_submitted,
                'payouts_enabled': account.payouts_enabled,
                'charges_enabled': account.charges_enabled,
                'requirements': account.requirements,
            }
            
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
