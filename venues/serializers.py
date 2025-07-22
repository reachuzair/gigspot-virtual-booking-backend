from venues.models import VenueProof
from rest_framework import serializers

class VenueProofSerializer(serializers.ModelSerializer):
    class Meta:
        model = VenueProof
        fields = ["id", "venue", "document", "url", "uploaded_at"]
        read_only_fields = ["id", "uploaded_at", "venue"]

    def validate(self, data):
        if not data.get("document") and not data.get("url"):
            raise serializers.ValidationError("Either a document or URL must be provided.")
        return data
