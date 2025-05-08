# views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login, logout
from .models import User, Artist, Venue, Fan, ROLE_CHOICES
from .serializers import UserCreateSerializer, UserSerializer
from utils.email import send_templated_email
from django.utils import timezone
from payments.utils import create_stripe_account
from django.db import transaction
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    try:
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        
        role = serializer.validated_data.get('role', ROLE_CHOICES.FAN)
        stripe_response = None
        
        # Start atomic transaction (DB + Stripe)
        with transaction.atomic():
            # 1. Create User
            user = serializer.save()
            
            # 2. Create Role Profile (Artist/Venue/Fan)
            if role == ROLE_CHOICES.ARTIST:
                artist = Artist.objects.create(user=user)
            elif role == ROLE_CHOICES.VENUE:
                venue = Venue.objects.create(user=user)
            elif role == ROLE_CHOICES.FAN:
                Fan.objects.create(user=user)
            
            # 3. Create Stripe Account (if Artist/Venue)
            if role in [ROLE_CHOICES.ARTIST, ROLE_CHOICES.VENUE]:
                stripe_response = create_stripe_account(request, user)
                if not stripe_response:
                    raise Exception('Stripe account creation failed')
                
                # 4. Update Artist/Venue with Stripe ID
                if role == ROLE_CHOICES.ARTIST:
                    artist.stripe_account_id = stripe_response['stripe_account'].id
                    artist.save()
                else:
                    venue.stripe_account_id = stripe_response['stripe_account'].id
                    venue.save()
        
        return Response({
            'user': UserSerializer(user).data,
            'stripe_account': stripe_response['stripe_account'].id if stripe_response else None,
            'link': stripe_response['link'].url if stripe_response else None,
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        # Transaction will auto-rollback if any step fails
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT'])
@permission_classes([AllowAny])
def verify_otp(request):
    try:
        email = request.data.get('email')
        otp = request.data.get('otp')
        
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if user.ver_code != otp:
            return Response({"detail": "Invalid OTP"}, status=status.HTTP_400_BAD_REQUEST)
        
        if user.ver_code_expires < timezone.now():
            return Response({"detail": "OTP expired"}, status=status.HTTP_400_BAD_REQUEST)
        
        user.email_verified = True
        user.ver_code = None
        user.ver_code_expires = None
        user.save()
        
        return Response({"detail": "Email verified successfully", "user": UserSerializer(user).data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([AllowAny])
def resend_otp(request, email):
    try:
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if user.email_verified:
            return Response({"detail": "Email already verified"}, status=status.HTTP_400_BAD_REQUEST)
        
        otp = user.gen_otp()
        send_templated_email('OTP Verification', [user.email], 'otp_verification', {'otp': otp})
        
        return Response({"detail": "OTP sent successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    try:
        email = request.data.get('email')
        password = request.data.get('password')
        
        user = User.objects.filter(email=email).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
        
        if not user.check_password(password):
            return Response({"detail": "Invalid password"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not user.email_verified:
            return Response({"detail": "Email not verified"}, status=status.HTTP_400_BAD_REQUEST)
        
        login(request, user)
        
        return Response({"detail": "Login successful", "user": UserSerializer(user).data}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    try:
        logout(request)  # No need to pass user explicitly
        return Response({"detail": "Logout successful"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['GET'])
@permission_classes([AllowAny])
def forgot_password(request):
    email = request.query_params.get('email')

    user = User.objects.filter(email=email).first()
    if not user:
        return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
    
    otp = user.gen_otp()
    send_templated_email('OTP Verification', [user.email], 'otp_verification', {'otp': otp})
    
    return Response({"detail": "OTP sent successfully"}, status=status.HTTP_200_OK)
    
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def change_password(request):
    user = request.user
    password = request.data.get('password')
    old_password = request.data.get('old_password')
    
    if not password:
        return Response({"detail": "Password is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    if not old_password:
        return Response({"detail": "Old password is required"}, status=status.HTTP_400_BAD_REQUEST)
    
    if not user.check_password(old_password):
        return Response({"detail": "Invalid old password"}, status=status.HTTP_400_BAD_REQUEST)
    
    user.set_password(password)
    user.save()
    
    return Response({"detail": "Password changed successfully"}, status=status.HTTP_200_OK)
    
@api_view(['PUT'])
@permission_classes([AllowAny])
def reset_password(request):
    # Get data from the request
    new_password = request.data.get('new_password')
    email = request.data.get('email')

    if not new_password or not email:
        return Response(
            {"detail": _("new password, email are required")},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"detail": "Invalid user"}, status=status.HTTP_400_BAD_REQUEST)


