from rest_framework import serializers
from custom_auth.models import Artist

class ArtistSerializer(serializers.ModelSerializer):
    class Meta:
        model = Artist
        fields = '__all__'
        extra_kwargs = {field: {'required': True} for field in fields if field != 'id'}