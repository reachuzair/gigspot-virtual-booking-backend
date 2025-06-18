from dj_rest_auth.registration.serializers import SocialLoginSerializer
from rest_framework import serializers

class CustomSocialLoginSerializer(SocialLoginSerializer):
    role = serializers.ChoiceField(
        choices=[
            ('artist', 'Artist'),
            ('venue', 'Venue'),
            ('fan', 'Fan')
        ],
        required=True
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        role = self.initial_data.get("role")
        if not role:
            raise serializers.ValidationError({"role": "Role is required."})
        return attrs