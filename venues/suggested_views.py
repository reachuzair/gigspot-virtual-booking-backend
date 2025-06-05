from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Case, When, Value, BooleanField
from django.utils import timezone
from datetime import timedelta

from custom_auth.models import Venue
from users.serializers import VenueProfileSerializer

class SuggestedVenuesView(APIView):
    """
    API endpoint to get suggested venues based on subscription tiers.
    Returns venues with active subscriptions, ordered by tier priority.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Get all venues with active subscriptions
        active_venues = Venue.objects.filter(
            ad_subscriptions__status='active',
            ad_subscriptions__current_period_end__gt=timezone.now()
        ).distinct()

        # Annotate venues with their highest active subscription tier
        # Premium (3) > Boosted (2) > Starter (1)
        venues_with_tier = active_venues.annotate(
            tier_priority=Case(
                When(ad_subscriptions__plan__name='PREMIUM', then=Value(3)),
                When(ad_subscriptions__plan__name='BOOSTED', then=Value(2)),
                When(ad_subscriptions__plan__name='STARTER', then=Value(1)),
                default=Value(0),
                output_field=BooleanField(),
            ),
            is_featured=Case(
                When(ad_subscriptions__plan__name__in=['PREMIUM', 'BOOSTED'], then=Value(True)),
                default=Value(False),
                output_field=BooleanField(),
            )
        ).order_by('-tier_priority', '?')  # Randomize within same tier

        # Get the serialized data
        serializer = VenueProfileSerializer(
            venues_with_tier, 
            many=True,
            context={'request': request}
        )

        # Add subscription tier info to each venue
        response_data = []
        for venue_data in serializer.data:
            venue = Venue.objects.get(id=venue_data['id'])
            active_sub = venue.ad_subscriptions.filter(
                status='active',
                current_period_end__gt=timezone.now()
            ).select_related('plan').first()
            
            if active_sub:
                venue_data['subscription_tier'] = {
                    'name': active_sub.plan.get_name_display(),
                    'is_featured': active_sub.plan.name in ['PREMIUM', 'BOOSTED'],
                    'is_premium': active_sub.plan.name == 'PREMIUM',
                    'features': active_sub.plan.features
                }
                response_data.append(venue_data)

        return Response({
            'count': len(response_data),
            'results': response_data
        })
