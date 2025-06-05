# views.py
from rest_framework import status, generics, viewsets
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet, ViewSet
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
import stripe
from django.conf import settings

from custom_auth.models import Venue
from .models import (
    SubscriptionPlan, ArtistSubscription,
    VenueAdPlan, VenueSubscription
)
from .serializers import (
    SubscriptionPlanSerializer, ArtistSubscriptionSerializer,
    VenueAdPlanSerializer, VenueSubscriptionSerializer,
    CreateVenueSubscriptionSerializer
)

stripe.api_key = settings.STRIPE_SECRET_KEY


class VenueAdPlanViewSet(viewsets.ViewSet):
    """
    API endpoint that allows venue ad plans to be viewed.
    """
    permission_classes = [IsAuthenticated]
    
    def list(self, request):
        queryset = VenueAdPlan.objects.filter(is_active=True).order_by('monthly_price')
        serializer = VenueAdPlanSerializer(queryset, many=True)
        return Response(serializer.data)
    
    def retrieve(self, request, pk=None):
        queryset = VenueAdPlan.objects.filter(is_active=True)
        plan = get_object_or_404(queryset, pk=pk)
        serializer = VenueAdPlanSerializer(plan)
        return Response(serializer.data)


class VenueSubscriptionViewSet(ModelViewSet):
    """
    API endpoint that allows venue subscriptions to be viewed or edited.
    """
    serializer_class = VenueSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Only return subscriptions for venues owned by the current user
        return VenueSubscription.objects.filter(
            venue__user=self.request.user
        ).select_related('plan').order_by('-created_at')
    
    def get_serializer_class(self):
        if self.action == 'create':
            return CreateVenueSubscriptionSerializer
        return VenueSubscriptionSerializer
    
    def perform_create(self, serializer):
        # Get the venue from the request data or URL
        venue_id = self.request.data.get('venue_id')
        if not venue_id:
            raise serializers.ValidationError({'venue_id': 'This field is required.'})
        
        try:
            venue = Venue.objects.get(id=venue_id, user=self.request.user)
        except Venue.DoesNotExist:
            raise serializers.ValidationError({'venue_id': 'Venue not found or you do not have permission.'})
        
        # Check for existing active subscription
        existing_sub = VenueSubscription.objects.filter(
            venue=venue,
            status='active',
            current_period_end__gt=timezone.now()
        ).exists()
        
        if existing_sub:
            raise serializers.ValidationError(
                'This venue already has an active subscription.'
            )
        
        # In a real implementation, you would create a Stripe subscription here
        # For now, we'll create a subscription with a test Stripe ID
        serializer.save(
            venue=venue,
            status='active',
            stripe_subscription_id=f'sub_test_{int(timezone.now().timestamp())}',
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timedelta(days=30)
        )
    
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a subscription at the end of the current billing period"""
        subscription = self.get_object()
        
        if subscription.status != 'active':
            return Response(
                {'error': 'Only active subscriptions can be cancelled.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        subscription.cancel_at_period_end = True
        subscription.save()
        
        # In a real implementation, you would update the subscription in Stripe
        # stripe.Subscription.modify(
        #     subscription.stripe_subscription_id,
        #     cancel_at_period_end=True
        # )
        
        return Response({'status': 'subscription will be cancelled at period end'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_venue_subscription_status(request, venue_id):
    """
    Get the subscription status for a specific venue
    """
    try:
        venue = Venue.objects.get(id=venue_id, user=request.user)
    except Venue.DoesNotExist:
        return Response(
            {'detail': 'Venue not found or you do not have permission'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    active_subscription = VenueSubscription.objects.filter(
        venue=venue,
        status='active',
        current_period_end__gt=timezone.now()
    ).select_related('plan').first()
    
    if not active_subscription:
        return Response({'has_active_subscription': False})
    
    serializer = VenueSubscriptionSerializer(active_subscription)
    return Response({
        'has_active_subscription': True,
        'subscription': serializer.data
    })

@api_view(['GET'])
def subscription_plans(request):
    """Get available subscription plans"""
    plans = SubscriptionPlan.objects.filter(is_active=True)
    serializer = SubscriptionPlanSerializer(plans, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def payment_methods(request):
    return Response(stripe.PaymentMethod.list())

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_artist_subscription(request):
    user = request.user
    data = request.data
    
    try:
        # Verify user is an artist
        if not hasattr(user, 'artist'):
            return Response(
                {'error': 'Only artists can subscribe for plans.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        artist = user.artist
        plan_id = data.get('plan_id')
        payment_method = data.get('payment_method')
        
        if not plan_id or not payment_method:
            return Response(
                {'error': 'Plan ID and payment method are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get the plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {'error': 'Invalid subscription plan'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if artist already has a subscription
        if hasattr(artist, 'subscription'):
            return Response(
                {'error': 'Artist already has a subscription'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create or retrieve Stripe customer
        customer_data = {
            'email': user.email,
            'name': user.name if user.name else user.name,
            'payment_method': payment_method,
            'invoice_settings': {'default_payment_method': payment_method},
            'metadata': {'artist_id': artist.id}
        }
        
        if hasattr(artist, 'subscription') and artist.subscription.stripe_customer_id:
            customer = stripe.Customer.modify(
                artist.subscription.stripe_customer_id,
                **customer_data
            )
        else:
            customer = stripe.Customer.create(**customer_data)
        
        # Create subscription
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{'price': plan.stripe_price_id}],
            payment_settings={'save_default_payment_method': 'on_subscription'},
            expand=['latest_invoice'],
            metadata={'artist_id': artist.id}
        )

        # Get payment intent separately if needed
        # latest_invoice = stripe.Invoice.retrieve(
        #     subscription.latest_invoice.id,
        #     expand=['payment_intent']
        # )
        print(subscription)
        # Save subscription details
        ArtistSubscription.objects.create(
            artist=artist,
            stripe_customer_id=customer.id,
            stripe_subscription_id=subscription.id,
            plan=plan,
            status=subscription.status,
            current_period_end=datetime.fromtimestamp(subscription['items']['data'][0]['current_period_end'])
        )
        
        # Update artist's subscription tier
        artist.subscription_tier = plan.subscription_tier
        artist.save()
        
        return Response({
            'subscription_id': subscription.id,
            # 'client_secret': latest_invoice.payment_intent.client_secret if hasattr(latest_invoice, 'payment_intent') else None,
            'status': subscription.status,
            'current_period_end': subscription['items']['data'][0]['current_period_end']
        })
        
    except Exception as e:
        return Response(
            {'detail': str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def test_create_artist_subscription(request):
    """
    Test endpoint for creating a subscription directly with card details.
    (For development/testing only - DO NOT use in production)
    """
    user = request.user
    data = request.data

    try:
        # Verify user is an artist
        if not hasattr(user, 'artist'):
            return Response(
                {'error': 'Only artists can subscribe for plans.'},
                status=status.HTTP_403_FORBIDDEN
            )

        artist = user.artist
        plan_id = data.get('plan_id')
        card_number = data.get('card_number')
        card_exp_month = data.get('card_exp_month')
        card_exp_year = data.get('card_exp_year')
        card_cvc = data.get('card_cvc')

        # Validate input
        if not all([plan_id, card_number, card_exp_month, card_exp_year, card_cvc]):
            return Response(
                {'error': 'Plan ID and full card details are required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Get the plan
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id)
        except SubscriptionPlan.DoesNotExist:
            return Response(
                {'error': 'Invalid subscription plan'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if artist already has a subscription
        if hasattr(artist, 'subscription'):
            return Response(
                {'error': 'Artist already has a subscription'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Step 1: Create a Stripe PaymentMethod
        payment_method = stripe.PaymentMethod.create(
            type='card',
            card={
                'number': card_number,
                'exp_month': card_exp_month,
                'exp_year': card_exp_year,
                'cvc': card_cvc,
            },
        )

        # Step 2: Create/update Stripe Customer
        customer_data = {
            'email': user.email,
            'name': user.name if user.name else user.name,
            'payment_method': payment_method.id,
            'invoice_settings': {'default_payment_method': payment_method.id},
            'metadata': {'artist_id': artist.id}
        }

        if hasattr(artist, 'subscription') and artist.subscription.stripe_customer_id:
            customer = stripe.Customer.modify(
                artist.subscription.stripe_customer_id,
                **customer_data
            )
        else:
            customer = stripe.Customer.create(**customer_data)

        # Step 3: Create Subscription
        subscription = stripe.Subscription.create(
            customer=customer.id,
            items=[{'price': plan.stripe_price_id}],
            expand=['latest_invoice.payment_intent'],
            metadata={'artist_id': artist.id}
        )

        # Save subscription details
        ArtistSubscription.objects.create(
            artist=artist,
            stripe_customer_id=customer.id,
            stripe_subscription_id=subscription.id,
            plan=plan,
            status=subscription.status,
            current_period_end=datetime.fromtimestamp(subscription.current_period_end)
        )

        # Update artist's subscription tier
        artist.subscription_tier = plan.subscription_tier
        artist.save()

        return Response({
            'subscription_id': subscription.id,
            'client_secret': subscription.latest_invoice.payment_intent.client_secret,
            'status': subscription.status,
            'current_period_end': subscription.current_period_end,
            'payment_method_id': payment_method.id  # For debugging
        })

    except Exception as e:
        return Response(
            {'error': str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def manage_artist_subscription(request):
    user = request.user
    
    if not hasattr(user, 'artist') or not hasattr(user.artist, 'subscription'):
        return Response(
            {'error': 'No active subscription found'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'GET':
        """Get current subscription details"""
        subscription = user.artist.subscription
        subscription.update_from_stripe()  # Sync with Stripe
        serializer = ArtistSubscriptionSerializer(subscription)
        return Response(serializer.data)

    elif request.method == 'POST':
        """Cancel or update subscription"""
        artist = user.artist
        subscription = artist.subscription
        action = request.data.get('action')
        
        try:
            if action == 'cancel':
                # Cancel at period end
                stripe_sub = stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=True
                )
                subscription.status = stripe_sub.status
                subscription.cancel_at_period_end = True
                subscription.save()
                
                return Response({
                    'status': 'success',
                    'message': 'Subscription will cancel at period end',
                    'cancel_at': stripe_sub.cancel_at
                })
                
            elif action == 'reactivate':
                # Reactivate canceled subscription
                stripe_sub = stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    cancel_at_period_end=False
                )
                subscription.status = stripe_sub.status
                subscription.cancel_at_period_end = False
                subscription.save()
                
                return Response({
                    'status': 'success',
                    'message': 'Subscription reactivated'
                })
                
            elif action == 'change_plan':
                # Change subscription plan
                new_plan_id = request.data.get('plan_id')
                if not new_plan_id:
                    return Response(
                        {'error': 'Plan ID required'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    new_plan = SubscriptionPlan.objects.get(id=new_plan_id)
                except SubscriptionPlan.DoesNotExist:
                    return Response(
                        {'error': 'Invalid subscription plan'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                # Update subscription in Stripe
                stripe_sub = stripe.Subscription.modify(
                    subscription.stripe_subscription_id,
                    items=[{
                        'id': stripe.Subscription.retrieve(
                            subscription.stripe_subscription_id
                        ).items.data[0].id,
                        'price': new_plan.stripe_price_id,
                    }],
                    proration_behavior='create_prorations'
                )
                
                # Update local records
                subscription.plan = new_plan
                subscription.status = stripe_sub.status
                subscription.current_period_end = datetime.fromtimestamp(stripe_sub.current_period_end)
                subscription.save()
                
                # Update artist's subscription tier
                artist.subscription_tier = new_plan.subscription_tier
                artist.save()
                
                return Response({
                    'status': 'success',
                    'message': 'Subscription plan updated',
                    'new_plan': SubscriptionPlanSerializer(new_plan).data
                })
            
            else:
                return Response(
                    {'error': 'Invalid action'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )