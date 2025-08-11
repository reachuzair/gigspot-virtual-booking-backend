# views.py
from rest_framework.permissions import AllowAny
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth import login, logout
from .models import User, Artist, Venue, Fan, ROLE_CHOICES
from .serializers import ArtistSerializer, FanSerializer, UserCreateSerializer, UserSerializer, VenueSerializer
from utils.email import send_templated_email
from django.utils import timezone
from payments.utils import create_stripe_account
from django.db import transaction
from django.contrib.auth.backends import ModelBackend
import logging
from rest_framework_simplejwt.tokens import RefreshToken
logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
def signup(request):
    try:
        serializer = UserCreateSerializer(data=request.data)
        if not serializer.is_valid():
            # Extract the first validation error and convert it to a generic format
            first_key = next(iter(serializer.errors), None)
            if first_key:
                first_error = serializer.errors[first_key]
                message = first_error[0] if isinstance(first_error, list) else str(first_error)
                field_label = str(first_key).replace('_', ' ').capitalize()
                return Response({"detail": f"{message}"}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": "Invalid data provided."}, status=status.HTTP_400_BAD_REQUEST)

        role = serializer.validated_data.get('role', ROLE_CHOICES.FAN)
        stripe_response = None

        with transaction.atomic():
            # 1. Create User
            user = serializer.save()
            profile_data = getattr(user, 'profile_data', {})

            # 2. Create Role Profile
            if role == ROLE_CHOICES.ARTIST:
                artist = Artist.objects.create(
                    user=user,
                    full_name=profile_data.get("full_name"),
                    phone_number=profile_data.get("phone_number"),
                    band_name=profile_data.get("band_name"),
                    band_email=profile_data.get("band_email"),
                    logo=profile_data.get("logo"),
                    city=profile_data.get("city"),
                    state=profile_data.get("state"),
                )
            elif role == ROLE_CHOICES.VENUE:
                proof_type = profile_data.get("proof_type")
                proof_document = profile_data.get("proof_document") if proof_type == "DOCUMENT" else None
                proof_url = profile_data.get("proof_url") if proof_type == "URL" else None

                profile_data_cleaned = {
                    k: v for k, v in profile_data.items()
                    if k not in ["proof_type", "proof_document", "proof_url"]
                }

                venue = Venue.objects.create(
                    user=user,
                    proof_type=proof_type,
                    proof_document=proof_document,
                    proof_url=proof_url,
                    **profile_data_cleaned
                )
            elif role == ROLE_CHOICES.FAN:
                fan = Fan.objects.create(user=user)

            # 3. Create Stripe Account
            if role in [ROLE_CHOICES.ARTIST, ROLE_CHOICES.VENUE]:
                stripe_response = create_stripe_account(request, user)
                if not stripe_response:
                    raise Exception('Stripe account creation failed')

                stripe_account_id = stripe_response['stripe_account'].id
                onboarding_link = stripe_response['link'].url

                # 4. Save Stripe details
                if role == ROLE_CHOICES.ARTIST:
                    artist.stripe_account_id = stripe_account_id
                    artist.stripe_onboarding_link = onboarding_link
                    artist.save()
                elif role == ROLE_CHOICES.VENUE:
                    venue.stripe_account_id = stripe_account_id
                    venue.stripe_onboarding_link = onboarding_link 
                    venue.save()

        # 5. Response
        response_data = {
            'user': UserSerializer(user).data,
            'stripe_account': stripe_response['stripe_account'].id if stripe_response else None,
            'link': stripe_response['link'].url if stripe_response else None,
        }

        if role == ROLE_CHOICES.ARTIST:
            response_data['artist'] = ArtistSerializer(artist).data
        elif role == ROLE_CHOICES.VENUE:
            response_data['venue'] = VenueSerializer(venue).data
        elif role == ROLE_CHOICES.FAN:
            response_data['fan'] = FanSerializer(fan).data

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)




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
        send_templated_email('OTP Verification', [
                             user.email], 'otp_verification', {'otp': otp})

        return Response({"detail": "OTP sent successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

from stripe import Account, AccountLink
def generate_stripe_onboarding_link(user, stripe_account_id):
    link = AccountLink.create(
        account=stripe_account_id,
        refresh_url="https://www.gigspotvb.com/stripe/refresh",  # Adjust to your frontend
        return_url="https://www.gigspotvb.com/stripe/return",    # Adjust to your frontend
        type="account_onboarding"
    )
    return link.url


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    """
    Email / password login.
    Returns:
      • JWT refresh token
      • JWT access token
      • Serialized user object
      • Stripe onboarding link (if applicable)
    """
    try:
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password')

        user = User.objects.filter(email__iexact=email).first()
        if not user:
            return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)

        if not user.check_password(password):
            return Response({"detail": "Invalid password"}, status=status.HTTP_400_BAD_REQUEST)

        if not user.email_verified:
            return Response({"detail": "Email not verified"}, status=status.HTTP_400_BAD_REQUEST)

        if not getattr(user, 'backend', None):
            user.backend = f"{ModelBackend.__module__}.{ModelBackend.__name__}"

        login(request, user)

        refresh = RefreshToken.for_user(user)
        onboarding_link = None

        # Stripe logic based on role
        if user.role == ROLE_CHOICES.ARTIST:
            artist = getattr(user, 'artist_profile', None)
            if artist and artist.stripe_account_id:
                account = Account.retrieve(artist.stripe_account_id)
                if not account.details_submitted:
                    onboarding_link = generate_stripe_onboarding_link(user, artist.stripe_account_id)
                    artist.stripe_onboarding_link = onboarding_link
                    artist.save()
                else:
                    artist.stripe_onboarding_completed = True
                    artist.save()

        elif user.role == ROLE_CHOICES.VENUE:
            venue = getattr(user, 'venue_profile', None)
            account = Account.retrieve(venue.stripe_account_id)

            if not account.details_submitted:
                onboarding_link = generate_stripe_onboarding_link(user, venue.stripe_account_id)
                venue.stripe_onboarding_link = onboarding_link
                venue.save()
            else:
                venue.stripe_onboarding_completed = True
                venue.save()
        # Response
        return Response({
            "detail": "Login successful",
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": UserSerializer(user).data,
            "stripe_onboarding_link": onboarding_link
        }, status=status.HTTP_200_OK)

    except Exception as e:
        print("Login view error:", str(e))
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
    send_templated_email('OTP Verification', [
                         user.email], 'otp_verification', {'otp': otp})

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

    if user.check_password(password):
        return Response({"detail": "New password cannot be the same as the old password"}, status=status.HTTP_400_BAD_REQUEST)

    user.set_password(password)
    user.save()

    return Response({"detail": "Password changed successfully"}, status=status.HTTP_200_OK)

@api_view(['PUT'])
@permission_classes([AllowAny])
def reset_password(request):
    new_password = request.data.get('new_password')
    email = request.data.get('email')

    if not new_password or not email:
        return Response(
            {"detail": "new password and email are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)

        if user.check_password(new_password):
            return Response({"detail": "New password cannot be the same as the old password"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password reset successful"}, status=status.HTTP_200_OK)

    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({"detail": "Invalid user"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    user = request.user
    password = request.data.get('password')

    if not password:
        return Response({"detail": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Re-authenticate the user
    if not user.check_password(password):
        return Response({"detail": "Incorrect password."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        # Use a transaction to ensure atomicity
        with transaction.atomic():
            # Manually delete related objects first to avoid cascade recursion
            
            # Delete notifications first (this is likely the source of recursion)
            if hasattr(user, 'notifications'):
                user.notifications.all().delete()
            
            # Delete gig-related objects
            if hasattr(user, 'created_gigs'):
                user.created_gigs.all().delete()
            if hasattr(user, 'gig_invites_sent'):
                user.gig_invites_sent.all().delete()
            
            # Delete profile objects (these should cascade properly)
            if hasattr(user, 'artist_profile'):
                user.artist_profile.delete()
            if hasattr(user, 'venue_profile'):
                user.venue_profile.delete()
            if hasattr(user, 'fan'):
                user.fan.delete()
            
            # Finally delete the user
            user.delete()
                
        return Response({"detail": "Account deleted successfully."}, status=status.HTTP_200_OK)
        
    except Exception as e:
        logger.error(f"Error deleting user account: {str(e)}")
        return Response({"detail": "An error occurred while deleting the account."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)