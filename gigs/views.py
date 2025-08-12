from asyncio.log import logger
from datetime import timedelta
import stripe
from rest_framework import serializers
from custom_auth.serializers import VenueSerializer
from gigspot_backend import settings
from .models import Gig, Status, GigType
import io
import logging
import math
import random
import string
from django.core.cache import cache
from django.db.models import Q, Prefetch, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from rest_framework import status, filters, generics
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import TourStatus, TourVenueSuggestion
from .serializers_tour import TourSerializer
from custom_auth.permissions import IsPremiumUser
from chat.models import ChatRoom, Message
from PIL import ImageFont, ImageDraw
from datetime import datetime
from custom_auth.models import ROLE_CHOICES, Venue, Artist, User, PerformanceTier
from rt_notifications.utils import create_notification
from utils.email import send_templated_email
from django.utils.timezone import now
from .models import Gig, Contract, GigInvite, GigType, Status, GigInviteStatus, Tour, TourVenueSuggestion
from .serializers import (
    GigSerializer,
    ContractSerializer,
    VenueEventSerializer,
    GigDetailSerializer
)
from .serializers_tour import TourVenueSuggestionSerializer, BookedVenueSerializer
from .utils import PricingValidationError
from django.core.exceptions import ValidationError as DjangoValidationError

# Initialize logger
logger = logging.getLogger(__name__)

# Create your views here.


class GigPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'per_page'
    max_page_size = 100


@api_view(['GET'])
def list_gigs(request):
    import math
    user = request.user if request.user.is_authenticated else None
    gig_type = request.query_params.get('type')  # 'artist_gig' or 'venue_git'

    # Get filter parameters
    location = request.query_params.get('location')
    radius = int(request.query_params.get('radius', 30))
    search_query = request.query_params.get('search', '')

    # Base queryset
    gigs = Gig.objects.all()

    # Apply visibility rules based on authentication and user role
    if user and user.is_authenticated:
        if hasattr(user, 'artist'):
            # For artists:
            # 1. Their own gigs (created by them or where they're a collaborator)
            # 2. All public gigs from other artists
            # 3. All venue gigs
            gigs = gigs.filter(
                (Q(created_by=user) | Q(collaborators=user)) |
                (Q(gig_type=GigType.ARTIST_GIG, is_public=True, status='approved')) |
                (Q(gig_type=GigType.VENUE_GIG, status='approved'))
            )
        elif hasattr(user, 'venue_profile'):
            # For venues:
            # 1. Their own gigs (created by them)
            # 2. All public artist gigs
            # 3. All other venue gigs
            gigs = gigs.filter(
                Q(created_by=user) |
                (Q(venue=user.venue_profile)) |
                (Q(gig_type=GigType.ARTIST_GIG, is_public=True, status='approved')) |
                (Q(gig_type=GigType.VENUE_GIG, status='approved'))
            )
        elif hasattr(user, 'fan'):
            # Fans can only see approved artist gigs
            gigs = gigs.filter(status='approved', gig_type=GigType.ARTIST_GIG)
    else:
        # Unauthenticated users see nothing
        gigs = gigs.none()

    # Filter by gig type if specified
    if gig_type in [gt[0] for gt in GigType.choices]:
        gigs = gigs.filter(gig_type=gig_type)

    # Filter by search query
    if search_query:
        gigs = gigs.filter(Q(title__icontains=search_query)
                           | Q(description__icontains=search_query))

    # Filter by location if provided
    if location:
        try:
            lat_str, lon_str = location.split(',')
            user_lat, user_lon = float(lat_str), float(lon_str)
        except Exception:
            return Response(
                {'detail': 'Invalid location format. Use lat,lon'},
                status=status.HTTP_400_BAD_REQUEST
            )

        def haversine(lat1, lon1, lat2, lon2):
            R = 3958.8  # Radius of earth in miles
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi/2)**2 + math.cos(phi1) * \
                math.cos(phi2)*math.sin(dlambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c

        gigs_in_radius = []
        for gig in gigs:
            venue = gig.venue
            if not venue or not venue.location or len(venue.location) < 2:
                continue

            try:
                venue_lat, venue_lon = float(
                    venue.location[0]), float(venue.location[1])
                distance = haversine(user_lat, user_lon, venue_lat, venue_lon)
                if distance <= radius:
                    gigs_in_radius.append(gig.id)
            except (ValueError, TypeError):
                continue

        gigs = gigs.filter(id__in=gigs_in_radius)

    # Order by most recent first
    gigs = gigs.order_by('-created_at')

    # Initialize paginator
    paginator = GigPagination()

    # Create cache key
    page = request.query_params.get('page', 1)
    per_page = request.query_params.get('per_page', 10)
    cache_key = f"gig_list_{location}_{radius}_{search_query}_{gig_type}_page_{page}_perpage_{per_page}"

    # Check cache
    cached_response = cache.get(cache_key)
    if cached_response is not None:
        # Return cached response with proper pagination structure
        return Response({
            'count': len(cached_response),
            'next': None,  # These would need to be calculated if you want proper pagination links
            'previous': None,
            'results': cached_response
        })

    # Paginate and serialize if not in cache
    result_page = paginator.paginate_queryset(gigs, request)
    serializer = GigSerializer(
        result_page,
        many=True,
        context={'request': request}
    )

    # Cache for 5 minutes
    cache.set(cache_key, serializer.data, timeout=60*5)
    return paginator.get_paginated_response(serializer.data)


class GigDetailView(APIView):
    """
    Retrieve a gig by ID with detailed information
    """
    permission_classes = []  # Handle authentication manually

    def get(self, request, id):
        try:
            gig = Gig.objects.get(id=id)
            serializer = GigDetailSerializer(gig, context={'request': request})
            return Response(serializer.data)
        except Gig.DoesNotExist:
            return Response(
                {'detail': 'Gig not found'},
                status=status.HTTP_404_NOT_FOUND
            )

    def _can_view_gig(self, user, gig):
        # Unauthenticated users can only see approved public gigs
        if not user or not user.is_authenticated:
            return gig.status == 'approved' and gig.is_public

        # Admin can see everything
        if user.is_staff:
            return True

        # Creator can always see their own gigs
        if gig.created_by == user:
            return True

        # Check user role-based visibility
        if hasattr(user, 'artist'):
            # Artists can see their collaborations, their own gigs, venue gigs, or public artist gigs
            return (
                gig.created_by == user or
                user in gig.collaborators.all() or
                gig.gig_type == GigType.VENUE_GIG or
                (gig.gig_type == GigType.ARTIST_GIG and gig.is_public)
            )
        elif hasattr(user, 'venue_profile'):
            # Venues can see gigs at their venue, or public gigs
            return (
                gig.venue == user.venue_profile or
                (gig.gig_type == GigType.ARTIST_GIG and gig.is_public) or
                gig.gig_type == GigType.VENUE_GIG
            )
        elif hasattr(user, 'fan'):
            # Fans can see all approved gigs
            return gig.status == 'approved'

        # Default deny
        return False


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_venue_event(request):
    """
    Create a new venue event.
    Only venue users can create venue events.
    """
    user = request.user

    # Check if user is a venue
    if not hasattr(user, 'venue_profile') or not user.venue_profile:
        return Response(
            {'detail': 'Only venue users with a valid venue can create venue events'},
            status=status.HTTP_403_FORBIDDEN
        )

    venue = user.venue_profile  

    data = request.data.copy()

    data['gig_type'] = GigType.VENUE_GIG
    data['status'] = Status.APPROVED
    data['venue'] = venue.id  
    data['created_by'] = user.id

    if 'title' not in data:
        data['title'] = f"Event at {venue.venue_name}"
    if 'description' not in data:
        data['description'] = f"Event hosted by {venue.venue_name}"

    if 'flyer_image' in request.FILES:
        data['flyer_image'] = request.FILES['flyer_image']


    max_artists = int(data.get('max_artists', 1))
    max_tickets = int(data.get('max_tickets', 1))

    if max_artists > venue.artist_capacity:
        return Response(
            {'detail': f'Maximum artists cannot exceed venue capacity of {user.name}, which is {venue.artist_capacity} artists'},
            status=status.HTTP_400_BAD_REQUEST
        )

    if max_tickets > venue.capacity:
        return Response(
            {'detail': f'Maximum tickets cannot exceed venue capacity of {venue.user.name}, which is {venue.capacity} people'},
            status=status.HTTP_400_BAD_REQUEST
        )

    serializer = VenueEventSerializer(data=data, context={'request': request})

    if serializer.is_valid():
        gig = serializer.save(
            gig_type=GigType.VENUE_GIG,
            venue=venue,
            created_by=user,
            status=data.get('status', Status.APPROVED)
        )

        create_notification(
            user=user,
            notification_type='venue_event_created',
            message=f'Successfully created venue event: {gig.title}',
            **gig.__dict__
        )
        response_serializer = GigSerializer(gig, context={'request': request})

        return Response({
            'status': 'success',
            'data': response_serializer.data,
            'message': 'Venue event created successfully'
        }, status=status.HTTP_201_CREATED)

    # --- Generic error formatting ---
    # If validation fails
    errors = serializer.errors
    first_key = next(iter(errors), None)
    if first_key:
        message = errors[first_key][0] if isinstance(errors[first_key], list) else errors[first_key]
        field_name = str(first_key).replace('_', ' ').capitalize()
        return Response({"detail": f"{message}"}, status=status.HTTP_400_BAD_REQUEST)

    # Default fallback
    return Response({"detail": "Validation failed"}, status=status.HTTP_400_BAD_REQUEST)




class LikeGigView(APIView):
    """
    Like or unlike a gig
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        try:
            gig = Gig.objects.get(id=id)
            user = request.user

            if gig.likes.filter(id=user.id).exists():
                gig.likes.remove(user)
                liked = False
            else:
                gig.likes.add(user)
                liked = True

            # Save the gig to persist the like/unlike action
            gig.save()

            return Response({
                'status': 'success',
                'liked': liked,
                'likes_count': gig.likes.count()
            })

        except Gig.DoesNotExist:
            return Response(
                {'detail': 'Gig not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class UserLikedGigsView(APIView):
    """
    List all gigs liked by the current user, with optional filters
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        print(f"Fetching liked gigs for user: {user.id} - {user.email}")

        # Base queryset: gigs liked by the user
        liked_gigs = Gig.objects.filter(likes=user)

        # Optional filter: city
        city = request.query_params.get('city')
        if city:
            liked_gigs = liked_gigs.filter(venue__city__iexact=city)  # case-insensitive exact match
            print(f"Filtering gigs by city: {city}")

        # Order by newest
        liked_gigs = liked_gigs.order_by('-created_at')
        print(f"Found {liked_gigs.count()} liked gigs for user {user.id}")

        # Serialize the results
        serializer = GigSerializer(
            liked_gigs,
            many=True,
            context={'request': request}
        )

        print(f"Serialized {len(serializer.data)} gigs for user {user.id}")

        return Response({
            'status': 'success',
            'count': liked_gigs.count(),
            'results': serializer.data
        })


class UpcomingGigsView(generics.ListAPIView):
    """
    List upcoming gigs. If user is a FAN and ?artist_id=<id> is provided,
    return gigs for that artist only.
    """
    serializer_class = GigSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter,
                       DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['title', 'description', 'venue__name']
    ordering_fields = ['event_date', 'created_at']
    filterset_fields = ['gig_type', 'status']

    def get_queryset(self):
        now = timezone.now()
        user = self.request.user
        artist_id = self.kwargs.get('artist_id')

        queryset = Gig.objects.filter(event_date__gte=now, status='approved')

        if user.role == ROLE_CHOICES.FAN and artist_id:
            queryset = queryset.filter(
                Q(collaborators__id=artist_id) |
                Q(created_by__id=artist_id)
            )

        queryset = queryset.exclude(
            Q(created_by=user) | Q(collaborators=user)
        )

        return queryset.distinct().order_by('event_date')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_invite_request(request, id):
    user = request.user

    if user.role not in ['venue', 'artist']:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data.copy()
    artist_id = data.get('artist')
    if not artist_id:
        return Response({'detail': 'artist value missing'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
        if gig.created_by != user:
            return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        artist = Artist.objects.get(id=artist_id)

        # 1. Create gig invite
        gig_invite = GigInvite.objects.create(
            status=GigInviteStatus.PENDING,
            gig=gig,
            user=user,
            artist_received=artist
        )

        # 2. Create or get chat room
        room, _ = ChatRoom.objects.get_or_create_between_users(user, artist.user)

        # 3. Send invite message in chat
        Message.objects.create(
            chat_room=room,
            sender=user,
            receiver=artist.user,
            content={
                "invite_id": gig_invite.id,
                "type": "invite",
            }
        )

        # 4. System notification (optional)
        create_notification(
            user,
            'system',
            'Gig invitation sent',
            **gig.__dict__
        )

        return Response(
            {'message': 'Gig invitation sent successfully'},
            status=status.HTTP_201_CREATED
        )

    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def accept_invite_request(request, id):
    user = request.user

    if user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    owner_id = request.data.get('owner')
    if not owner_id:
        return Response({'detail': 'owner value missing'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        owner = User.objects.get(id=owner_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        artist = Artist.objects.get(user=user)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        gig_invite = GigInvite.objects.filter(
            gig=gig, user=owner, artist_received=artist, status='pending'
        ).first()

        if not gig_invite:
            return Response({'detail': 'Gig invite not found'}, status=status.HTTP_404_NOT_FOUND)

        # Accept invite
        gig_invite.status = GigInviteStatus.ACCEPTED
        gig_invite.save()

        # Add artist to gig
        gig.invitees.add(artist)
        gig.collaborators.add(artist.user)
        gig.save()

        room, _ = ChatRoom.objects.get_or_create_between_users(user, owner)

        Message.objects.create(
            chat_room=room,
            sender=user,
            receiver=owner,
            content={
                "type": "invite_accepted",
                "invite_id": gig_invite.id
            }
        )

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Notification and response
    create_notification(request.user, 'system', 'Gig invite accepted', **gig.__dict__)
    
    serializer = GigSerializer(gig)
    return Response({
        'gig': serializer.data,
        'message': 'Gig invite accepted successfully'
    }, status=status.HTTP_201_CREATED)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def reject_invite_request(request, id):
    user = request.user

    if user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    owner_id = request.data.get('owner')
    if not owner_id:
        return Response({'detail': 'owner value missing'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        owner = User.objects.get(id=owner_id)
    except User.DoesNotExist:
        return Response({'detail': 'User not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        artist = Artist.objects.get(user=user)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        gig_invite = GigInvite.objects.filter(
            gig=gig, user=owner, artist_received=artist, status='pending'
        ).first()

        if not gig_invite:
            return Response({'detail': 'Gig invite not found'}, status=status.HTTP_404_NOT_FOUND)

        gig_invite.status = GigInviteStatus.REJECTED
        gig_invite.save()

        
        room, _ = ChatRoom.objects.get_or_create_between_users(user, owner)

        Message.objects.create(
            chat_room=room,
            sender=user,
            receiver=owner,
            content={
                "type": "invite_rejected",
                "invite_id": gig_invite.id,
            }
        )

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # System notification and response
    create_notification(request.user, 'system', 'Gig invite rejected', **gig.__dict__)

    serializer = GigSerializer(gig)
    return Response({
        'gig': serializer.data,
        'message': 'Gig invite rejected successfully'
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_gig(request):
    try:
        # Ensure we have a valid request object with data
        if not hasattr(request, 'data'):
            return Response(
                {'detail': 'Invalid request data'},
                status=status.HTTP_400_BAD_REQUEST
            )
        user = request.user

        if not hasattr(user, 'role') or user.role not in [ROLE_CHOICES.VENUE, ROLE_CHOICES.ARTIST]:
            return Response(
                {'detail': 'Unauthorized - Only artists and venues can create gigs'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Safely get request data
        data = request.data.copy() if hasattr(request, 'data') else {}
        venue_id = data.get('venue_id')

        if not venue_id:
            return Response(
                {'detail': 'venue_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            venue = Venue.objects.get(id=venue_id)
        except (Venue.DoesNotExist, ValueError):
            return Response(
                {'detail': 'Venue not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Prepare data for serializer
        serializer_data = {
            'venue_id': venue.id,
            'created_by': user.id,
            'max_artist': data.get('max_artist', venue.artist_capacity),
            **{k: v for k, v in data.items() if k != 'venue_id'}
        }

        serializer = GigSerializer(
            data=serializer_data, context={'request': request})
        if serializer.is_valid():
            gig = serializer.save()
            if hasattr(request, 'user'):
                create_notification(
                    request.user,
                    'system',
                    'Gig created successfully',
                    **{'gig_id': gig.id, 'title': gig.title}
                )
            return Response(
                {
                    'gig': serializer.data,
                    'message': 'Gig created successfully'
                },
                status=status.HTTP_201_CREATED
            )

        return Response(
            {'detail': 'Validation error', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    except Exception as e:
        return Response(
            {'detail': f'An error occurred: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_gig_type(request, id):
    user = request.user

    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data.copy()
    is_public = data.get('is_public', None)

    if is_public is None:
        return Response({'detail': 'is_public value missing'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    if timezone.now() > gig.created_at + timedelta(minutes=10):
        gig.status = Status.TIMED_OUT 
        gig.save()
        return Response({'detail': 'Gig creation timed out. Please start again.'},
                        status=status.HTTP_408_REQUEST_TIMEOUT)
    try:
        gig.is_public = is_public
        gig.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    serializer = GigSerializer(gig)

    create_notification(request.user, 'system',
                        'Gig status updated successfully', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig status updated successfully'
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_gig_details(request, id):
    user = request.user

    if user.role not in [ROLE_CHOICES.VENUE, ROLE_CHOICES.ARTIST]:
        return Response(
            {"detail": "Unauthorized: only Venue or Artist can perform this action."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({"detail": f'Gig with ID {id} not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({"detail": f'Error fetching gig: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Timeout logic
    if timezone.now() > gig.created_at + timedelta(minutes=10):
        gig.status = Status.TIMED_OUT
        gig.save()
        return Response({'detail': 'Gig creation timed out. Please start again.'},
                        status=status.HTTP_408_REQUEST_TIMEOUT)

    data = request.data.copy()

    if 'flyer_bg' in request.FILES:
        data['flyer_bg'] = request.FILES['flyer_bg']

    # Validate max_tickets
    try:
        max_tickets = int(data.get('max_tickets', 0))
    except ValueError:
        return Response({'detail': 'max_tickets must be an integer.'}, status=status.HTTP_400_BAD_REQUEST)

    if max_tickets <= 0:
        return Response({'detail': 'max_tickets must be greater than zero.'}, status=status.HTTP_400_BAD_REQUEST)

    # Get venue and check capacity
    try:
        venue = Venue.objects.get(id=gig.venue_id)
    except Venue.DoesNotExist:
        return Response({'detail': f'Venue with ID {gig.venue_id} not found.'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        return Response({'detail': f'Error fetching venue: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if max_tickets > venue.capacity:
        return Response({
            'detail': f'Max tickets value ({max_tickets}) exceeds venue capacity ({venue.capacity}).'
        }, status=status.HTTP_400_BAD_REQUEST)

    # Auto-set artist capacity
    data['max_artist'] = venue.artist_capacity

    # Serialize and save
    serializer = GigSerializer(
        gig, data=data, partial=True, context={"request": request}
    )

    if serializer.is_valid():
        try:
            gig = serializer.save()
        except DjangoValidationError as e:
            return Response(
                {"detail": " ".join(e.messages)},
                status=status.HTTP_400_BAD_REQUEST
            )

        create_notification(request.user, 'system',
                            'Gig created successfully', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig created successfully'
        }, status=status.HTTP_201_CREATED)

    # Handle errors — clean up __all__ to be generic
    error_messages = []
    for field, messages in serializer.errors.items():
        for msg in messages:
            if field == "__all__":
                error_messages.append(msg)  # Generic message
            else:
                error_messages.append(f"{field}: {msg}")

    return Response(" | ".join(error_messages), status=status.HTTP_400_BAD_REQUEST)


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def add_gig_venue_fee(request, id):
    user = request.user

    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    data = request.data.copy()
    venue_fee = data.get('venue_fee')

    if venue_fee is None:
        # Use venue's reservation_fee if no venue_fee is provided
        venue_fee = user.venue.reservation_fee if hasattr(user, 'venue') else 0

    gig.venue_fee = venue_fee
    gig.save()

    serializer = GigSerializer(gig)

    create_notification(request.user, 'system',
                        'Gig venue fee updated successfully', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig venue fee updated successfully'
    }, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_gig_status(request, id):
    user = request.user

    if user.role not in [ROLE_CHOICES.VENUE]:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    data = request.data.copy()
    new_status = data.get('status', None)

    if new_status is None:
        return Response({'detail': 'status value missing'}, status=status.HTTP_400_BAD_REQUEST)

    allowed_status = ['approved', 'rejected']
    if new_status not in allowed_status:
        return Response({'detail': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        gig.status = new_status
        gig.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    serializer = GigSerializer(gig)

    create_notification(request.user, 'system',
                        'Gig status updated successfully', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig status updated successfully'
    }, status=status.HTTP_201_CREATED)


def generate_contract_pdf(contract):
    """
    Generate a PDF contract with the given contract details.

    Args:
        contract: Contract instance containing the details to include in the PDF

    Returns:
        BytesIO object containing the generated PDF
    """

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)

    # Create styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'title',
        parent=styles['Heading1'],
        fontSize=24,
        spaceAfter=30
    )

    content_style = ParagraphStyle(
        'content',
        parent=styles['Normal'],
        fontSize=12,
        spaceAfter=15
    )

    elements = []

    # Add contract title
    elements.append(Paragraph("CONTRACT AGREEMENT", title_style))

    # Add contract details
    elements.append(
        Paragraph(f"Venue: {contract.venue.user.name}", content_style))
    elements.append(
        Paragraph(f"Artist: {contract.artist.user.name}", content_style))
    elements.append(Paragraph(f"Venue Fee: ${contract.price}", content_style))
    elements.append(Paragraph(f"Gig: {contract.gig.name}", content_style))
    elements.append(
        Paragraph(f"Ticket Price: ${contract.gig.ticket_price}", content_style))
    elements.append(
        Paragraph(f"Event Date: {contract.gig.event_date.date()}", content_style))
    elements.append(
        Paragraph(f"Contract Date: {contract.created_at.date()}", content_style))

    # requests_to_artist = [
    #     req for req in contract.request_message.split('. ') if req.strip()]

    # elements.append(Spacer(1, 20))
    # for req in requests_to_artist:
    #     elements.append(Paragraph(req, content_style))

    # Add terms and conditions
    terms = [
        "Terms and Conditions:",
        "1. The artist agrees to perform the services as described.",
        "2. The recipient agrees to pay the agreed amount of ${contract.price}.",
        "3. Any changes must be agreed upon by both parties.",
        "4. This contract is legally binding."
    ]

    elements.append(Spacer(1, 20))
    for term in terms:
        elements.append(Paragraph(term, content_style))

    # Add signatures
    elements.append(Spacer(1, 50))
    elements.append(
        Paragraph("Venue Signature: ________________________", content_style))
    elements.append(
        Paragraph("Artist Signature: ________________________", content_style))

    # Build the PDF
    doc.build(elements)

    # Get the value of the BytesIO buffer and write it to the response.
    pdf = buffer.getvalue()
    buffer.close()

    return pdf


def generate_contract_image(contract):
    """
    Generate a contract image with the given contract details.

    Args:
        contract: Contract instance containing the details to include in the image

    Returns:
        BytesIO object containing the generated image
    """
    image = Image.new('RGB', (800, 1200), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype("arial.ttf", 32)
        font_content = ImageFont.truetype("arial.ttf", 20)
    except:
        font_title = ImageFont.load_default()
        font_content = ImageFont.load_default()

    y = 40
    line_spacing = 36
    small_spacing = 28

    # Title
    draw.text((50, y), "CONTRACT AGREEMENT", font=font_title, fill=(0, 0, 0))
    y += line_spacing + 10

    # Contract details
    draw.text((50, y), f"Venue: {contract.venue.user.name}",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text((50, y), f"Artist: {contract.artist.user.name}",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text((50, y), f"Venue Fee: ${contract.price}",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text((50, y), f"Gig: {contract.gig.name}",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text(
        (50, y), f"Ticket Price: ${contract.gig.ticket_price}", font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text(
        (50, y), f"Event Date: {contract.gig.event_date.date()}", font=font_content, fill=(0, 0, 0))
    y += small_spacing
    draw.text(
        (50, y), f"Contract Date: {contract.created_at.date()}", font=font_content, fill=(0, 0, 0))
    y += small_spacing

    # Requests to Artist (split at '. ')
    # requests_to_artist = [
    #     req for req in contract.request_message.split('. ') if req.strip()]
    # if requests_to_artist:
    #     y += 12
    #     draw.text((50, y), "Requests to Venue:",
    #               font=font_content, fill=(0, 0, 0))
    #     y += small_spacing
    #     for req in requests_to_artist:
    #         draw.text((70, y), f"- {req}", font=font_content, fill=(0, 0, 0))
    #         y += small_spacing

    # Terms and conditions
    terms = [
        "Terms and Conditions:",
        "1. The artist agrees to perform the services as described.",
        f"2. The recipient agrees to pay the agreed amount of ${contract.price}.",
        "3. Any changes must be agreed upon by both parties.",
        "4. This contract is legally binding."
    ]
    y += 20
    for term in terms:
        draw.text((50, y), term, font=font_content, fill=(0, 0, 0))
        y += small_spacing

    # Signatures
    y += 30
    draw.text((50, y), "Venue Signature: ________________________",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing + 10
    draw.text((50, y), "Artist Signature: ________________________",
              font=font_content, fill=(0, 0, 0))
    y += small_spacing

    # Save the image to BytesIO
    image_io = io.BytesIO()
    image.save(image_io, format='PNG')
    image_io.seek(0)
    return image_io


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_contract(request, gig_id):
    user = request.user
    price = float(request.data.get('price', 0))

    if price <= 0:
        return Response({'detail': 'Price cannot be less than or equal to 0'}, status=status.HTTP_400_BAD_REQUEST)
    try:

        gig = Gig.objects.get(id=gig_id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        artist = Artist.objects.get(user=gig.created_by.id)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        venue = Venue.objects.get(id=gig.venue_id)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)

    try:

        # Create a new contract (adjust fields as needed)
        contract = Contract.objects.create(
            artist=artist,  # assuming user has an artist profile
            venue=venue,  # assuming you pass venue_id in request
            gig=gig,
            price=price
        )

        # Generate contract PDF
        pdf = generate_contract_pdf(contract)
        image = generate_contract_image(contract)

        # Save the PDF to the contract
        pdf_buffer = io.BytesIO(pdf)
        contract.pdf.save(f'contract_{contract.id}.pdf', pdf_buffer)
        contract.image.save(f'contract_{contract.id}.png', image)
        contract.save()

        # Return the PDF as response
        pdf_buffer.seek(0)
        return Response({'contract': {'id': contract.id, 'artist': artist.user.name, 'venue': venue.user.name, 'gig': gig.id, 'pdf_url': contract.pdf.url, 'image_url': contract.image.url}}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_contract(request, contract_id):
    user = request.user

    if user.role == ROLE_CHOICES.VENUE:
        try:
            venue = Venue.objects.get(user=user)
            contract = Contract.objects.get(id=contract_id, venue=venue)
        except Contract.DoesNotExist:
            return Response({'detail': 'Contract not found'}, status=status.HTTP_404_NOT_FOUND)
    elif user.role == ROLE_CHOICES.ARTIST:
        try:
            artist = Artist.objects.get(user=user)
            contract = Contract.objects.get(id=contract_id)
        except Contract.DoesNotExist:
            return Response({'detail': 'Contract not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = ContractSerializer(contract)
    return Response({'contract': serializer.data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_contract_by_gig(request, gig_id):
    user = request.user

    if user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        artist = Artist.objects.get(user=user)
        gig = Gig.objects.get(id=gig_id)
        contracts = Contract.objects.filter(
            gig=gig).order_by('-created_at')

        if not contracts.exists():
            return Response({'detail': 'Contract not found'}, status=status.HTTP_404_NOT_FOUND)

        contract = contracts.first()
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ContractSerializer(contract)
    return Response({'contract': serializer.data})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def sign_contract(request, contract_id):
    user = request.user
    contract_pin = request.data.get('contract_pin')
    application_fee = int(request.data.get('application_fee', 0))
    is_host = request.data.get('is_host', False)

    # Validate contract pin from cache
    cached_pin = cache.get(f"contract_pin:{user.id}")
    if not contract_pin or contract_pin != cached_pin:
        return Response({'detail': 'Invalid or expired contract pin'}, status=400)

    # Clear pin after use
    cache.delete(f"contract_pin:{user.id}")

    # Get the correct contract based on role
    try:
        if user.role == ROLE_CHOICES.ARTIST:
            artist = Artist.objects.get(user=user)
            contract = Contract.objects.get(id=contract_id)
            contract.artist_signed = True
        elif user.role == ROLE_CHOICES.VENUE:
            venue = Venue.objects.get(user=user)
            contract = Contract.objects.get(id=contract_id, venue=venue)
            contract.venue_signed = True
        else:
            return Response({'detail': 'Unauthorized role'}, status=403)
    except (Artist.DoesNotExist, Venue.DoesNotExist):
        return Response({'detail': 'User profile not found'}, status=404)
    except Contract.DoesNotExist:
        return Response({'detail': 'Contract not found'}, status=404)

    contract.save()

    # Handle artist payment intent
    if user.role == ROLE_CHOICES.ARTIST:
        collaborators = list(contract.gig.collaborators.all())
        if user not in collaborators and user != contract.gig.created_by:
            collaborators.append(user)
            total_artists = len(collaborators)
        else:
            total_artists = 1

        

        if total_artists == 1:
            reason = "Only one artist involved. Full amount sent to venue."
        elif total_artists == 2:
            reason = "Two artists involved. 50% amount sent to first collaborator."
        else:
            reason = f"{total_artists} artists involved. Full amount sent to first collaborator."
        logger.info(
            f"contract.venue.stripe_account_id: {contract.venue.stripe_account_id}")
        intent = stripe.PaymentIntent.create(
            amount=(
                int(contract.price * 100) if total_artists == 1 else
                int((contract.price * 100) // 2) if total_artists == 2 else
                int(contract.price * 100)
            ),
            currency="usd",
            transfer_data={
                "destination": (
                    contract.venue.stripe_account_id if total_artists == 1 else
                    collaborators[0].stripe_account_id
                )

            },
            metadata={
                "contract_id": contract.id,
                "payment_intent_for": "contract_signature",
                "is_host": is_host,
                "total_artists": total_artists,
                "payout_reason": reason,
                "initiated_by_user": str(user.id),
            }
        )
        logger.info(f"PaymentIntent created: {intent.id} for contract {contract.id}")
        return Response({
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id
        })

    return Response({'detail': 'Contract signed successfully'}, status=200)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_contract_pin(request):
    user = request.user
    pin = str(random.randint(100000, 999999))

    # Store the pin in cache for 60 minutes
    cache.set(f"contract_pin:{user.id}", pin, timeout=60 * 60)  # 1 hour

    # Send email
    send_templated_email(
        subject="Your Contract Verification PIN",
        recipient_list=[user.email],
        template_name="contract_pin",
        context={
            "name": user.name,
            "pin": pin,
            "message": "Your Contract PIN"
        }
    )

    return Response({
        'status': 'success',
        'message': 'A contract PIN has been sent to your email.'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def validate_ticket_price(request):
    """
    Validate a ticket price against the user's performance tier.

    Request body should include:
    - price: The ticket price to validate (required)
    - gig_id: Optional gig ID for updates (if applicable)
    """
    price = request.data.get('price')
    gig_id = request.data.get('gig_id')

    if price is None:
        return Response(
            {"error": "Price is required"},

            status=status.HTTP_400_BAD_REQUEST
        )
    try:
        price = float(price)
        if price < 0:
            raise ValueError("Price cannot be negative")
    except (ValueError, TypeError):
        return Response(
            {'detail': 'Invalid price format'},
            status=status.HTTP_400_BAD_REQUEST
        )

    # Get the user's performance tier (default to FRESH_TALENT if not an artist)
    performance_tier = PerformanceTier.FRESH_TALENT
    if hasattr(request.user, 'artist') and request.user.artist and request.user.artist.performance_tier:
        performance_tier = request.user.artist.performance_tier

    # If this is an update to an existing gig, get the gig
    gig = None
    if gig_id:
        try:
            gig = Gig.objects.get(id=gig_id, created_by=request.user)
        except Gig.DoesNotExist:
            return Response(
                {'detail': 'Gig not found or you do not have permission'},
                    status=status.HTTP_404_NOT_FOUND
                )

    # Create a temporary gig for validation if needed
    if not gig:
        gig = Gig(
            created_by=request.user,
            gig_type=GigType.ARTIST_GIG,
            ticket_price=price
            )
    else:
        gig.ticket_price = price

    # Get the validation result
    validation_result = gig.requires_price_confirmation(price=price)

    return Response({
        'is_valid': not validation_result['requires_confirmation'],
        'message': validation_result['message'],
        'suggested_range': validation_result['suggested_range'],
        'tier': performance_tier.label if hasattr(performance_tier, 'label') else performance_tier
    })



class TourVenueSuggestionsAPI(APIView):
    """
    Suggest venues based on cities from already suggested venues in a tour.
    Also allows booking (selecting) a venue in the tour via POST.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, tour_id):
        """
        Bulk select (book) venues for the tour.

        Expected POST data:
        {
            "venues": [
                { "venue_id": 123, "order": 1 },
                { "venue_id": 124, "order": 2 }
            ]
        }
        """
        try:
            tour = get_object_or_404(Tour, id=tour_id, artist__user=request.user)
            venues_data = request.data.get('venues')

            if not isinstance(venues_data, list) or not venues_data:
                return Response(
                    {"error": "A non-empty 'venues' list is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            booked_suggestions = []

            for item in venues_data:
                venue_id = item.get('venue_id')
                order = item.get('order', 0)

                if not venue_id:
                    continue  # Skip invalid entry

                venue = get_object_or_404(Venue, id=venue_id, is_completed=True)

                suggestion, _ = TourVenueSuggestion.objects.update_or_create(
                    tour=tour,
                    venue=venue,
                    defaults={
                        'order': order,
                        'is_booked': True
                    }
                )
                booked_suggestions.append(suggestion)

            serializer = BookedVenueSerializer(booked_suggestions, many=True)
            return Response(
                {
                    "message": "Venues booked successfully.",
                    "booked_venues": serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        except Exception as e:
            logger.error(f"Error in TourVenueSuggestionsAPI POST: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while booking venues."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    def get(self, request, tour_id):
        """
        Get venue suggestions based on already selected cities or selected_cities on the tour.
        """
        user = request.user
        tour = get_object_or_404(Tour, id=tour_id, artist__user=user)

        min_capacity = request.query_params.get('min_capacity')
        max_capacity = request.query_params.get('max_capacity')

        existing_suggestions = TourVenueSuggestion.objects.filter(tour=tour).select_related('venue')
        cities = list({
            s.venue.city for s in existing_suggestions if s.venue and s.venue.city
        })

        if not cities:
            cities = tour.selected_cities or []

        venues = Venue.objects.filter(is_completed=True, city__in=cities)

        if min_capacity:
            venues = venues.filter(capacity__gte=min_capacity)
        if max_capacity:
            venues = venues.filter(capacity__lte=max_capacity)

        suggested_ids = existing_suggestions.values_list('venue_id', flat=True)
        venues = venues.exclude(id__in=suggested_ids)

        serializer = VenueSerializer(venues, many=True, context={'request': request})
        return Response({
            "count": venues.count(),
            "results": serializer.data
        })

class SelectedTourVenuesView(APIView):
    """
    Returns the list of selected venues for a tour, including the custom order.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, tour_id):
        user = request.user
        tour = get_object_or_404(Tour, id=tour_id, artist__user=user)

        suggestions = TourVenueSuggestion.objects.filter(
            tour=tour
        ).select_related('venue').order_by('order', 'created_at')

        serializer = TourVenueSuggestionSerializer(suggestions, many=True, context={'request': request})
        return Response({
            "count": suggestions.count(),
            "results": serializer.data
        })



class TourViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows tours to be viewed or edited.
    Requires a premium subscription for all operations except listing and retrieving.
    """
    serializer_class = TourSerializer
    permission_classes = [IsAuthenticated]
    
    def get_permissions(self):
        """
        Instantiates and returns the list of permissions that this view requires.
        Read operations are allowed for all authenticated users,
        while write operations require a premium subscription.
        """
        if self.action in ['list', 'retrieve']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated, IsPremiumUser]
        return [permission() for permission in permission_classes]
        
    def has_incomplete_tour(self, artist):
        """Check if artist has any incomplete tours"""
        return Tour.objects.filter(
            artist=artist,
            status__in=[
                TourStatus.DRAFT,
                TourStatus.PLANNING,
                TourStatus.ANNOUNCED,
                TourStatus.IN_PROGRESS
            ]
        ).exists()

    def has_unconfirmed_booking(self, artist):
        """Check if artist has any unconfirmed tour bookings"""
        return TourVenueSuggestion.objects.filter(
            tour__artist=artist,
            is_booked=False
        ).exists()

    def perform_create(self, serializer):
        """
        Set the current user as the tour creator and verify:
        1. They have an active premium subscription
        2. They don't have any incomplete tours
        3. They don't have any unconfirmed bookings
        """
        artist = self.request.user.artist_profile
        
        # Check premium subscription
        if not hasattr(artist, 'subscription') or not artist.subscription.can_create_tour():
            raise serializers.ValidationError(
                "A premium subscription is required to create tours."
            )
            
        # Check for incomplete tours
        if self.has_incomplete_tour(artist):
            raise serializers.ValidationError(
                "You already have an incomplete tour. Please complete or cancel it before creating a new one."
            )
            
        # Check for unconfirmed bookings
        if self.has_unconfirmed_booking(artist):
            raise serializers.ValidationError(
                "You have unconfirmed venue bookings. Please confirm or cancel them before creating a new tour."
            )
            
        serializer.save(artist=artist)
        
    def perform_update(self, serializer):
        """
        Verify the user has an active premium subscription before updating a tour.
        """
        artist = self.request.user.artist_profile
        if not hasattr(artist, 'subscription') or not artist.subscription.can_create_tour():
            raise serializers.ValidationError(
                "A premium subscription is required to modify tours."
            )
        serializer.save()
    
    def get_queryset(self):
        """Return only tours created by the current user."""
        return Tour.objects.filter(artist__user=self.request.user)
    
    def perform_create(self, serializer):
        """Set the current user as the tour creator."""
        artist = get_object_or_404(Artist, user=self.request.user)
        serializer.save(artist=artist)
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete a tour instance.
        Returns a success message upon successful deletion.
        """
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(
            {"detail": "Tour successfully deleted."},
            status=status.HTTP_204_NO_CONTENT
        )


class BookedVenuesAPI(APIView):
    """
    API for managing booked venues in a tour.
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, tour_id):
        """
        Get all booked venues for a tour, ordered by event date.
        """
        try:
            # Get the tour and verify ownership
            tour = get_object_or_404(Tour, id=tour_id, artist__user=request.user)
            
            # Get all booked venues for this tour
            booked_venues = TourVenueSuggestion.get_booked_venues(tour_id)
            
            # Serialize the response
            serializer = BookedVenueSerializer(booked_venues, many=True)
            return Response({
                "count": booked_venues.count(),
                "results": serializer.data
            })
            
        except Exception as e:
            logger.error(f"Error in get_booked_venues: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while fetching booked venues"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def post(self, request, tour_id):
        """
        Book a venue for the tour.
        
        Expected POST data:
        {
            "venue_id": 123,
            "event_date": "2023-12-25"
        }
        """
        try:
            # Get the tour and verify ownership
            tour = get_object_or_404(Tour, id=tour_id, artist__user=request.user)
            
            # Get venue and validate
            venue_id = request.data.get('venue_id')
            event_date = request.data.get('event_date')
            
            if not venue_id or not event_date:
                return Response(
                    {"error": "Both venue_id and event_date are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            venue = get_object_or_404(Venue, id=venue_id, is_active=True)
            
            # Create or update the booking
            suggestion, created = TourVenueSuggestion.objects.update_or_create(
                tour=tour,
                venue=venue,
                defaults={
                    'event_date': event_date,
                    'is_booked': True
                }
            )
            
            # Serialize the response
            serializer = BookedVenueSerializer(suggestion)
            return Response(serializer.data, 
                         status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error in book_venue: {str(e)}", exc_info=True)
            return Response(
                {"error": "An error occurred while booking the venue"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class GigByCityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        city = request.query_params.get('city')
        if not city:
            return Response({"detail": "City parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        gigs = Gig.objects.filter(venue__city__iexact=city)
        serializer = GigDetailSerializer(
            gigs, many=True, context={'request': request})
        return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def invited_list(request, invite_id=None):
    user = request.user
    venue = Venue.objects.filter(user=user).first()

    # Try getting artist profile (for invited user)
    artist_profile = getattr(user, 'artist_profile', None)

    if invite_id:
        try:
            invite = GigInvite.objects.select_related(
                'gig', 'gig__venue', 'artist_received', 'artist_received__user'
            ).get(id=invite_id)
        except GigInvite.DoesNotExist:
            return Response({'detail': 'Invite not found'}, status=404)

        # Ensure current user is either the inviter or the invited artist
        if not (invite.user == user or (artist_profile and invite.artist_received == artist_profile)):
            return Response({'detail': 'Not authorized to view this invite'}, status=403)

        data = {
            "event_date": invite.gig.event_date,
            'invite_id': invite.id,
            'gig_id': invite.gig.id,
            'gig_title': invite.gig.title,
            'flyer_image': invite.gig.flyer_image.url if invite.gig.flyer_image else None,
            'status': invite.status,
            'sent_at': invite.created_at,
            'address': invite.gig.venue.address if invite.gig.venue else None,
        }
        return Response({'invite': data})

    # Get all invites where user is sender or receiver
    invites = GigInvite.objects.select_related(
        'gig', 'gig__venue', 'artist_received', 'artist_received__user'
    ).filter(
        Q(user=user) | Q(artist_received=artist_profile)
    )

    data = [
        {
            "event_date": invite.gig.event_date,
            'invite_id': invite.id,
            'gig_id': invite.gig.id,
            'gig_title': invite.gig.title,
            'flyer_image': invite.gig.flyer_image.url if invite.gig.flyer_image else None,
            'status': invite.status,
            'sent_at': invite.created_at,
            'address': invite.gig.venue.address if invite.gig.venue else None,
        }
        for invite in invites
    ]

    return Response({'Invites': data})





@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_requests(request):
    user = request.user
    if not hasattr(user, 'artist_profile'):
        return Response({'detail': 'Only artists can view received requests.'}, status=403)

    invites = GigInvite.objects.filter(
        artist_received=user.artist_profile).select_related('gig', 'user')
    data = [
        {
            
            'gig_id': invite.gig.id,
            'gig_title': invite.gig.title,
            'sent_by': invite.user.name,
            'status': invite.status,
            'received_at': invite.created_at
        } for invite in invites
    ]
    return Response({'my_requests': data})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def signed_events(request, contract_id=None):
    user = request.user

    # Determine whether user is artist or venue
    if hasattr(user, 'venue_profile') and user.venue_profile:
        role_filter = {'venue': user.venue_profile}
    elif hasattr(user, 'artist_profile') and user.artist_profile:
        role_filter = {'artist': user.artist_profile}
    else:
        return Response({'detail': 'Only artists or venues can view signed events.'}, status=403)

    if contract_id:
        # Detail view for single signed contract
        try:
            contract = Contract.objects.get(
                id=contract_id,
                artist_signed=True,
                venue_signed=True,
                **role_filter
            )
        except Contract.DoesNotExist:
            return Response({'detail': 'Signed event not found.'}, status=404)

        data = {
            'contract_id': contract.id,
            'gig_id': contract.gig.id,
            'gig_title': contract.gig.title,
            'gig_type': contract.gig.gig_type,
            'is_public': contract.gig.is_public,
            'event_date': contract.gig.event_date,
            'signed_at': contract.updated_at,
            'banner_image': contract.gig.flyer_image.url if contract.gig.flyer_image else None,
            'price': contract.price,
            'artist': {
                'id': contract.gig.created_by.id,
                'name': contract.gig.created_by.name,
            }
        }
        return Response({'signed_event': data})

    else:
        # List all signed contracts
        contracts = Contract.objects.filter(
            artist_signed=True,
            venue_signed=True,
            **role_filter
        ).select_related('gig')

        data = [
            {
                'contract_id': contract.id,
                'gig_id': contract.gig.id,
                'gig_title': contract.gig.title,
                'event_date': contract.gig.event_date,
                'signed_at': contract.updated_at,
                'banner_image': contract.gig.flyer_image.url if contract.gig.flyer_image else None,
                'price': contract.price
            }
            for contract in contracts
        ]
        return Response({'signed_events': data})




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def artist_event_history(request):
    user = request.user

    if hasattr(user, 'artist_profile'):
        # Artist: past gigs created by or collaborated on
        gigs = Gig.objects.filter(
            event_date__lt=timezone.now()
        ).filter(
            Q(created_by=user) | Q(collaborators=user)
        ).distinct().order_by('-event_date')

    elif hasattr(user, 'venue_profile'):
        venue = user.venue_profile
        # Venue: past gigs either created by or assigned to this venue
        gigs = Gig.objects.filter(
            event_date__lt=timezone.now()
        ).filter(
            Q(created_by=user) | Q(venue=venue)
        ).distinct().order_by('-event_date')

    else:
        return Response({'detail': 'Only artists or venues can access event history.'}, status=403)

    serializer = GigDetailSerializer(gigs, many=True, context={'request': request})
    return Response({
        "count": len(serializer.data),
        "events": serializer.data
    })




@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_venue_gigs(request):
    user = request.user

    if not hasattr(user, 'venue_profile') or user.venue_profile is None:
        return Response({'detail': 'Only venue users can view pending gigs.'}, status=403)

    gig_id = request.query_params.get('gig_id')

    if gig_id:
        try:
            gig = Gig.objects.get(
                id=gig_id,
                venue=user.venue_profile,
                status=Status.PENDING,
                gig_type=GigType.ARTIST_GIG
            )
        except Gig.DoesNotExist:
            return Response({'detail': 'Pending gig not found.'}, status=404)

        serializer = GigSerializer(gig, context={'request': request})
        return Response({'gig': serializer.data})

    # Otherwise, return all pending gigs
    pending_gigs = Gig.objects.filter(
        venue=user.venue_profile,
        status=Status.PENDING,
        gig_type=GigType.ARTIST_GIG
    ).order_by('-created_at')

    serializer = GigSerializer(
        pending_gigs, many=True, context={'request': request})

    return Response({
        "count": pending_gigs.count(),
        "pending_gigs": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_collab_payment_share(request, gig_id):
    user = request.user

    try:
        artist = Artist.objects.get(user=user)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist profile not found'}, status=404)

    try:
        gig = Gig.objects.get(id=gig_id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=404)

    # Get the artist's contract for this gig
    # contract = Contract.objects.filter(artist=artist, gig=gig).order_by('-created_at').first()
    # if not contract:
    #     return Response({'detail': 'No contract found for this gig'}, status=404)

    collaborators = list(gig.collaborators.all())

    if user not in collaborators:
        collaborators.append(user)

    total_artists = len(collaborators)
    if total_artists == 0:
        return Response({'detail': 'No collaborators found'}, status=400)
    if not gig.is_public and not gig.invitees.filter(id=user.id).exists():
        return Response({'detail': 'Access denied. You are not invited to this private gig.'}, status=403)


    total_fee = gig.venue_fee # in cents
    per_artist_share = total_fee // total_artists

    return Response({
        # "contract_id": contract.id,
        "gig_id": gig.id,
        "total_fee": total_fee,
        "total_artists": total_artists,
        "per_artist_share": per_artist_share,
        "currency": "usd"
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_user_gigs(request):
    """
    Get all gigs created by the artist, excluding gigs where a contract is signed by both artist and venue.
    """
    user = request.user

    if not hasattr(user, 'artist_profile'):
        return Response({'detail': 'Only artists can view their gigs.'}, status=403)

    # Get IDs of gigs that have fully signed contracts (both artist and venue)
    signed_gig_ids = Contract.objects.filter(
        artist_signed=True,
        venue_signed=True
    ).values_list('gig_id', flat=True).distinct()

    gigs = Gig.objects.filter(
        created_by=user
    ).exclude(
        id__in=signed_gig_ids
    ).order_by('-created_at')

    serializer = GigSerializer(gigs, many=True, context={'request': request})

    return Response({
        "count": gigs.count(),
        "gigs": serializer.data
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_event_by_date(request):
    user = request.user

    if not hasattr(user, 'venue_profile') or user.venue_profile is None:
        return Response({"detail": "Only venue users can access this endpoint."},
                        status=status.HTTP_403_FORBIDDEN)

    date_str = request.GET.get('date')
    if not date_str:
        return Response({"detail": "Date is required."}, status=status.HTTP_400_BAD_REQUEST)

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        venue = user.venue_profile 
        events = Gig.objects.filter(venue=venue, event_date__date=date) 

        serializer = GigDetailSerializer(events, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_gigs(request, gig_id=None):
    user = request.user

    # Ensure user is either artist or venue
    if not hasattr(user, 'artist_profile') and not hasattr(user, 'venue_profile'):
        return Response({'detail': 'Only artists or venues can view their gigs.'}, status=status.HTTP_403_FORBIDDEN)

    try:
        if gig_id:
            # Fetch gig by ID
            gig = Gig.objects.get(id=gig_id)

            # Role-based access control
            if hasattr(user, 'artist'):
                if gig.created_by == user or user in gig.collaborators.all():
                    pass
                else:
                    return Response({'detail': 'Unauthorized to view this gig'}, status=403)
            elif hasattr(user, 'venue_profile'):
                if gig.gig_type == GigType.VENUE_GIG and gig.created_by == user:
                    pass
                else:
                    return Response({'detail': 'Unauthorized to view this gig'}, status=403)

            serializer = GigDetailSerializer(gig, context={'request': request})
            return Response(serializer.data)

        else:
            # List all gigs based on role
            if hasattr(user, 'artist_profile'):
                gigs = Gig.objects.filter(
                    Q(created_by=user) | Q(collaborators=user)
                )
            else:  # venue
                gigs = Gig.objects.filter(
                    created_by=user,
                    gig_type=GigType.VENUE_GIG
                )

            gigs = gigs.order_by('-created_at').distinct()
            serializer = GigSerializer(gigs, many=True, context={'request': request})
            return Response(serializer.data)

    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
from django.core.mail import send_mail
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_cancel_collaboration(request):
    try:
        gig_id = request.data.get('gig_id')
        user = request.user
        email = user.email

        if not gig_id:
            return Response({"detail": "gig_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        gig = Gig.objects.filter(id=gig_id).first()
        if not gig:
            return Response({"detail": "Gig not found"}, status=status.HTTP_404_NOT_FOUND)

        if user not in gig.collaborators.all():
            return Response({"detail": "You are not a collaborator for this gig"}, status=status.HTTP_400_BAD_REQUEST)

        # Generate OTP
        otp = str(random.randint(100000, 999999))
        user.ver_code = otp
        user.ver_code_expires = timezone.now() + timedelta(minutes=10)
        user.save()

        # Send OTP via email
        send_mail(
            subject="Cancel Collaboration OTP",
            to=email,
            body=f"Your OTP for cancelling collaboration in '{gig.title}' is: {otp}"
        )

        return Response({"detail": "OTP sent to your registered email"}, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
