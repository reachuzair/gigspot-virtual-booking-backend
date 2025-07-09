from django.forms import IntegerField
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.db.models import Subquery, OuterRef, IntegerField, BooleanField, Value, Case, When, F
from django.utils import timezone

from custom_auth.models import Venue
from subscriptions.models import VenueSubscription
from subscriptions.models import VenueAdPlan
from users.serializers import VenueProfileSerializer


class SuggestedVenuesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()

        active_ad_subs = VenueSubscription.objects.filter(
            venue=OuterRef('pk'),
            status='active',
            current_period_end__gt=now,
            plan__subscription_tier__isnull=False 
        ).order_by('-created_at')

        tier_subquery = active_ad_subs.annotate(
            tier=F('plan__subscription_tier')
        ).values('tier')[:1]

        venues_with_tier = Venue.objects.annotate(
            subscription_tier=Subquery(tier_subquery),
            tier_priority=Case(
                When(subscription_tier='PREMIUM', then=Value(3)),
                When(subscription_tier='BOOSTED', then=Value(2)),
                When(subscription_tier='STARTER', then=Value(1)),
                default=Value(0),
                output_field=IntegerField()
            ),
            is_featured=Case(
                When(subscription_tier__in=['PREMIUM', 'BOOSTED'], then=Value(True)),
                default=Value(False),
                output_field=BooleanField()
            )
        ).filter(subscription_tier__isnull=False).order_by('-tier_priority', '?')

        serializer = VenueProfileSerializer(
            venues_with_tier,
            many=True,
            context={'request': request}
        )

        # Build final response
        response_data = []
        for venue, venue_data in zip(venues_with_tier, serializer.data):
            active_sub = venue.ad_subscriptions.filter(
                status='active',
                current_period_end__gt=now
            ).select_related('plan').first()

            if active_sub:
                tier_key = active_sub.plan.subscription_tier
                feature_map = VenueAdPlan.FEATURE_MAP.get(tier_key, {})

                venue_data['subscription_tier'] = {
                    'name': tier_key.capitalize(),
                    'is_featured': tier_key in ['PREMIUM', 'BOOSTED'],
                    'is_premium': tier_key == 'PREMIUM',
                    'features': feature_map
                }

                response_data.append(venue_data)

        return Response({
            'count': len(response_data),
            'results': response_data
        })
