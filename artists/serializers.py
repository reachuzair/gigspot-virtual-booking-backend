from rest_framework import serializers
from custom_auth.models import Artist
from gigs.models import Gig
from gigs.serializers import GigSerializer

class ArtistSerializer(serializers.ModelSerializer):
    userId = serializers.IntegerField(source='user.id', read_only=True)
    artistName = serializers.CharField(source='user.name', read_only=True)
    artistGenre = serializers.SerializerMethodField(read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    updatedAt = serializers.DateTimeField(source='updated_at', read_only=True)
    bannerImage = serializers.ImageField(source='logo', read_only=True)

    def get_artistGenre(self, obj):
        gig = Gig.objects.filter().first()
        return gig.genre if gig else None
    
    class Meta:
        model = Artist
        fields = [
            'id', 'userId', 'artistName', 'createdAt', 'updatedAt', 'bannerImage','artistGenre'
        ]
        extra_kwargs = {field: {'required': True} for field in fields if field != 'id'}



