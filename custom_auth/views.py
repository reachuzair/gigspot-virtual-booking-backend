# views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login
from .models import User, Artist, Venue, Fan, ROLE_CHOICES
from .serializers import UserCreateSerializer

@api_view(['POST'])
@permission_classes([AllowAny])
def signup_view(request):
    try:
        serializer = UserCreateSerializer(data=request.data)
        if serializer.is_valid():
            # Create the base user
            user = serializer.save()
        
            # Handle role-specific profile creation
            role = serializer.validated_data.get('role', ROLE_CHOICES.FAN)
            
            if role == ROLE_CHOICES.ARTIST:
                Artist.objects.create(
                    user=user,
                    first_name=request.data.get('first_name', ''),
                    last_name=request.data.get('last_name', '')
                )
            elif role == ROLE_CHOICES.VENUE:
                Venue.objects.create(
                    user=user,
                    name=request.data.get('name', '')
                )
            elif role == ROLE_CHOICES.FAN:
                Fan.objects.create(
                    user=user,
                    first_name=request.data.get('first_name', ''),
                    last_name=request.data.get('last_name', '')
                )
            
            return Response({
                'user': serializer.data,
                'message': f'{role.capitalize()} account created successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)