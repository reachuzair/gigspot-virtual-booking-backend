from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from custom_auth.models import User, Artist, Venue, Fan
from custom_auth.models import ROLE_CHOICES
from .models import UserSettings
from rt_notifications.utils import create_notification
from django.forms.models import model_to_dict
from django.core.files.storage import default_storage

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    try:
        user = request.user
        response_data = {
            'id': user.id,
            'email': user.email,
            'role': user.role
        }
        
        def get_artist_data(artist):
            artist_data = model_to_dict(artist, exclude=['verification_docs', 'logo'])
            artist_data['verification_docs'] = artist.verification_docs.url if artist.verification_docs else None
            artist_data['logo'] = artist.logo.url if artist.logo else None
            return artist_data
            
        def get_venue_data(venue):
            venue_data = model_to_dict(venue, exclude=['verification_docs'])
            venue_data['verification_docs'] = venue.verification_docs.url if venue.verification_docs else None
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
def update_profile_image(request):
    try:
        user = request.user
        
        # Check if file is in request.FILES
        if 'profileImage' not in request.FILES:
            return Response({"detail": "No image file provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        image_file = request.FILES['profileImage']
        
        # Validate file type
        allowed_types = ['image/jpeg', 'image/png', 'image/gif']
        if image_file.content_type not in allowed_types:
            return Response({"detail": "Invalid image type. Only JPEG, PNG, and GIF are allowed."},
                           status=status.HTTP_400_BAD_REQUEST)
        
        # Validate file size (e.g., 5MB limit)
        if image_file.size > 5 * 1024 * 1024:  # 5MB
            return Response({"detail": "Image file too large. Maximum size is 5MB."},
                           status=status.HTTP_400_BAD_REQUEST)
        
        # Save the image
        user.profileImage = image_file
        user.save()
        
        create_notification(user, 'system', 'Profile Image Updated', description='You have successfully updated your profile image.')
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
        
        allowed_keys = ['name', 'username']
        if key not in allowed_keys:
            return Response({"detail": "Invalid key"}, status=status.HTTP_400_BAD_REQUEST)

        if key == 'name':
            user.name = value
        elif key == 'username':
            if User.objects.filter(username=value).exists():
                return Response({"detail": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)
            user.username = value
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
