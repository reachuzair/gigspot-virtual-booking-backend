from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import User, Artist, Venue, Fan
from custom_auth.models import ROLE_CHOICES
from users.serializers import ArtistProfileSerializer, FanProfileSerializer,  VenueProfileSerializer
from .models import UserSettings
from rt_notifications.utils import create_notification
from django.forms.models import model_to_dict
from django.core.files.storage import default_storage
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
# Create your views here.


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    try:
        user = request.user
        response_data = {
            'id': user.id,
            'email': user.email,
            'role': user.role,
            "profileImage": user.profileImage.url if user.profileImage else None
        }

        def get_artist_data(artist):
            artist_data = model_to_dict(
                artist, exclude=['verification_docs', 'logo'])
            artist_data['verification_docs'] = artist.verification_docs.url if artist.verification_docs else None
            artist_data['logo'] = artist.logo.url if artist.logo else None
            
            # Default to 'free' tier
            artist_data['subscription_tier'] = 'free'
            
            # Update to 'premium' if they have an active premium subscription
            if hasattr(artist, 'subscription') and artist.subscription:
                if artist.subscription.status == 'active' and hasattr(artist.subscription, 'plan'):
                    # Ensure we only set 'premium' for actual premium subscriptions
                    if artist.subscription.plan.subscription_tier.upper() == 'PREMIUM':
                        artist_data['subscription_tier'] = 'premium'
                
            return artist_data

        def get_venue_data(venue):


            venue_data = model_to_dict(venue, exclude=['verification_docs', 'seating_plan'])
            venue_data['verification_docs'] = venue.verification_docs.url if venue.verification_docs else None
            venue_data['seating_plan'] = venue.seating_plan.url if venue.seating_plan else None



            return venue_data

        if user.role == ROLE_CHOICES.ARTIST:
            artist = Artist.objects.get(user=user)
            response_data['artist'] = get_artist_data(artist)
        elif user.role == ROLE_CHOICES.VENUE:
            venue = Venue.objects.get(user=user)
            response_data['venue'] = get_venue_data(venue)
        elif user.role == ROLE_CHOICES.FAN:
            fan = Fan.objects.get(user=user)
            response_data['fan'] = model_to_dict(fan)

        return Response(response_data)

    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser])
def update_profile_image(request):
    try:
        user = request.user
        print(f"User: {user.name}, ID: {user.id}")
        if 'profileImage' not in request.FILES:
            return Response({"detail": "No image file provided"}, status=status.HTTP_400_BAD_REQUEST)

        image_file = request.FILES['profileImage']
        print(
            f"Received file: {image_file.name}, size: {image_file.size}, type: {image_file.content_type}")
        allowed_types = ['image/jpeg', 'image/png', 'image/gif']
        if image_file.content_type not in allowed_types:
            return Response({"detail": "Invalid image type. Only JPEG, PNG, and GIF are allowed."},
                            status=status.HTTP_400_BAD_REQUEST)

        if image_file.size > 5 * 1024 * 1024:
            return Response({"detail": "Image file too large. Maximum size is 5MB."},
                            status=status.HTTP_400_BAD_REQUEST)
        print(
            f"Image file is valid: {image_file.name}, size: {image_file.size}, type: {image_file.content_type}")
        # Save the image
        user.profileImage = image_file
        print(f"Saving profile image for user: {user.name}, ID: {user.id}")
        user.save()
        print(f"Profile image updated for user: {user.name}, ID: {user.id}")
        create_notification(user, 'system', 'Profile Image Updated',
                            description='You have successfully updated your profile image.')
        return Response({
            "detail": "Profile image updated successfully",
            "image_url": user.profileImage.url if user.profileImage else None
        }, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_notification_settings(request):
    try:
        user = request.user
        key = request.data.get('key')
        value = request.data.get('value')

        if not key or not value:
            return Response({"detail": "Key and value are required"}, status=status.HTTP_400_BAD_REQUEST)

        user_settings = UserSettings.objects.filter(user=user).first()
        if not user_settings:
            user_settings = UserSettings.objects.create(user=user)

        allowed_keys = ['notify_by_email', 'notify_by_app']
        if key not in allowed_keys:
            return Response({"detail": "Invalid key"}, status=status.HTTP_400_BAD_REQUEST)

        if value not in [True, False]:
            return Response({"detail": "Value must be a boolean"}, status=status.HTTP_400_BAD_REQUEST)

        setattr(user_settings, key, value)
        user_settings.save()

        return Response({"detail": "Notification settings updated successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_user_profile(request):
    try:
        user = request.user
        key = request.data.get('key')
        value = request.data.get('value')

        if not key or not value:
            return Response({"detail": "Key and value are required"}, status=status.HTTP_400_BAD_REQUEST)

        allowed_keys = ['name', 'name']
        if key not in allowed_keys:
            return Response({"detail": "Invalid key"}, status=status.HTTP_400_BAD_REQUEST)

        if key == 'name':
            user.name = value
        elif key == 'name':
            if User.objects.filter(name=value).exists():
                return Response({"detail": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)
            user.name = value
        else:
            return Response({"detail": "Invalid key"}, status=status.HTTP_400_BAD_REQUEST)

        user.save()

        return Response({"detail": "Profile updated successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_user(request):
    try:
        user = request.user
        user.is_deleted = True
        user.is_active = False
        user.save()
        return Response({"detail": "User deleted successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def update_artist_soundcharts_uuid(request):
    """
    Update the artist's SoundCharts UUID and update their performance tier.
    """
    try:
        user = request.user
        soundcharts_uuid = request.data.get('soundcharts_uuid')

        if not soundcharts_uuid:
            return Response(
                {"detail": "Soundcharts UUID is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # Check if user has an artist role
        if user.role != 'artist':
            return Response(
                {"detail": "User is not an artist"}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # Get or create artist record
        artist, created = Artist.objects.get_or_create(user=user)
        
        # Only update if UUID has changed
        if artist.soundcharts_uuid == soundcharts_uuid:
            return Response(
                {
                    "detail": "Soundcharts UUID is already set to this value",
                    "tier": artist.get_performance_tier_display(),
                    "last_updated": artist.last_tier_update
                }, 
                status=status.HTTP_200_OK
            )
            
        # Update UUID
        artist.soundcharts_uuid = soundcharts_uuid
        
        # Get tier from SoundCharts
        from services.soundcharts import SoundChartsAPI
        soundcharts = SoundChartsAPI()
        result = soundcharts.get_artist_tier(soundcharts_uuid)
        
        if 'error' in result:
            # Save the UUID even if tier update fails, but include a warning
            artist.save()
            return Response(
                {
                    "detail": "Soundcharts UUID saved, but failed to update tier",
                    "error": result.get('error', 'Unknown error')
                }, 
                status=status.HTTP_200_OK
            )
        
        # Update artist tier and save
        artist.performance_tier = result['tier']
        artist.last_tier_update = timezone.now()
        artist.save()
        
        return Response(
            {
                "detail": "Soundcharts UUID and artist tier updated successfully",
                "tier": artist.get_performance_tier_display(),
                "last_updated": artist.last_tier_update
            }, 
            status=status.HTTP_200_OK
        )
        
    except Exception as e:
        logger.error(f"Error updating SoundCharts UUID: {str(e)}")
        return Response(
            {"detail": "An error occurred while updating SoundCharts UUID"}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_artist_metrics(request):
    """
    Get the current artist's metrics, updating them if they're stale
    """
    try:
        user = request.user
        if user.role != 'artist':
            return Response({"detail": "User is not an artist"}, status=status.HTTP_403_FORBIDDEN)
            
        artist = Artist.objects.get(user=user)
        
        # Update metrics if needed
        from custom_auth.utils import update_artist_metrics_if_needed
        was_updated = update_artist_metrics_if_needed(artist)
        
        response_data = {
            "tier": artist.get_performance_tier_display(),
            "tier_key": artist.performance_tier,
            "followers": artist.followers,
            "monthly_listeners": artist.monthly_listeners,
            "total_streams": artist.total_streams,
            "last_updated": artist.last_metrics_update,
            "metrics_just_updated": was_updated
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Artist.DoesNotExist:
        return Response({"detail": "Artist profile not found"}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET', 'PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    user = request.user
    profile = None
    serializer_class = None

    if user.role == ROLE_CHOICES.ARTIST:
        try:
            profile = user.artist
            serializer_class = ArtistProfileSerializer
        except Artist.DoesNotExist:
            return Response({'detail': 'Artist profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    elif user.role == ROLE_CHOICES.VENUE:
        try:
            profile = user.venue
            serializer_class = VenueProfileSerializer
        except Venue.DoesNotExist:
            return Response({'detail': 'Venue profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    elif user.role == ROLE_CHOICES.FAN:
        try:
            profile = user.fan
            serializer_class = FanProfileSerializer
        except Fan.DoesNotExist:
            return Response({'detail': 'Fan profile not found.'}, status=status.HTTP_404_NOT_FOUND)

    else:
        return Response({'detail': 'Invalid role.'}, status=status.HTTP_400_BAD_REQUEST)

    if request.method == 'GET':
        serializer = serializer_class(profile)
        return Response(serializer.data)

    serializer = serializer_class(
        profile, data=request.data, partial=(request.method == 'PATCH'))
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
