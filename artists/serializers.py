from rest_framework import serializers
from custom_auth.models import Artist

class ArtistSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.name', read_only=True)

    class Meta:
        model = Artist
        fields = [
            'id', 'user', 'verification_docs', 'logo', 'band_name', 'band_email', 'state',
            'performance_tier', 'subscription_tier', 'shows_created', 'active_collaborations',
            'soundcharts_uuid', 'buzz_score', 'onFireStatus', 'connections',
            'stripe_account_id', 'stripe_onboarding_completed', 'created_at', 'updated_at',
            'user_name'
        ]
        extra_kwargs = {field: {'required': True} for field in fields if field != 'id'}