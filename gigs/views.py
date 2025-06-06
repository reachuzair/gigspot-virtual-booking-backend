from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, filters, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.views import APIView
from django.utils import timezone
from django.db.models import Q, Prefetch, Count
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend

from .models import Gig, Contract, GigType, Status, GigInvite
from custom_auth.models import Venue, Artist, User
from rt_notifications.utils import create_notification
from .serializers import (
    GigSerializer, 
    ContractSerializer, 
    GigInviteSerializer,
    VenueEventSerializer,
    GigDetailSerializer
)
from PIL import Image
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gigs(request):
    """
    Get gigs based on user role and query parameters.
    Query params:
    - type: Filter by gig type ('artist_gig' or 'venue_gig')
    - status: Filter by gig status
    - upcoming: If 'true', only return upcoming gigs (event_date >= today)
    - venue: Filter by venue ID (for admins only)
    - page_size: Number of results per page (max 50)
    """
    user = request.user
    
    # Base queryset with select_related and prefetch_related for performance
    gigs = Gig.objects.select_related('venue', 'created_by').prefetch_related(
        Prefetch('collaborators', queryset=User.objects.only('id', 'username')),
        'invitees'
    )
    
    # Apply filters based on user role
    if hasattr(user, 'artist'):
        # For artists, show their created gigs and gigs they're invited to
        gigs = gigs.filter(
            Q(created_by=user) | 
            Q(invitees=user.artist)
        ).distinct()
    elif hasattr(user, 'venue'):
        # For venues, show their created gigs and gigs at their venue
        gigs = gigs.filter(
            Q(created_by=user) | 
            Q(venue=user.venue)
        ).distinct()
    else:
        # For other users, only show their created gigs
        gigs = gigs.filter(created_by=user)
    
    # Apply query filters
    gig_type = request.query_params.get('type')
    if gig_type in [gt[0] for gt in GigType.choices]:
        gigs = gigs.filter(gig_type=gig_type)
    
    status = request.query_params.get('status')
    if status:
        gigs = gigs.filter(status=status)
    
    upcoming = request.query_params.get('upcoming', '').lower() == 'true'
    if upcoming:
        gigs = gigs.filter(event_date__gte=timezone.now())
    
    # Apply venue filter (for admins)
    venue_id = request.query_params.get('venue')
    if venue_id and user.is_staff:
        gigs = gigs.filter(venue_id=venue_id)
    
    # Order by event date by default
    gigs = gigs.order_by('event_date')
    
    # Pagination
    paginator = PageNumberPagination()
    paginator.page_size = min(int(request.query_params.get('page_size', 10)), 50)
    
    # Create cache key
    cache_key = f"gigs_{user.id}_{request.META['QUERY_STRING']}_page_{request.query_params.get('page', 1)}"
    cached_response = cache.get(cache_key)
    
    if cached_response:
        return paginator.get_paginated_response(cached_response)
    
    # Get paginated results
    result_page = paginator.paginate_queryset(gigs, request)
    
    # Serialize the paginated results
    serializer = GigSerializer(result_page, many=True, context={'request': request})
    
    # Cache the results for 5 minutes
    cache.set(cache_key, serializer.data, timeout=300)
    
    # Return paginated response
    return paginator.get_paginated_response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_gigs(request):
    import math
    user = request.user
    per_page = int(request.query_params.get('per_page', 10))
    page = int(request.query_params.get('page', 1))
    gig_type = request.query_params.get('type')  # 'artist_gig' or 'venue_gig'
    
    paginator = PageNumberPagination()
    paginator.page_size = per_page

    # Get filter parameters
    location = request.query_params.get('location')
    radius = int(request.query_params.get('radius', 30))
    search_query = request.query_params.get('search', '')
    
    # Base queryset - only show approved gigs
    gigs = Gig.objects.filter(status='approved')
    
    # Filter by gig type if specified
    if gig_type in [gt[0] for gt in GigType.choices]:
        gigs = gigs.filter(gig_type=gig_type)
    
    # Filter by search query
    if search_query:
        gigs = gigs.filter(Q(title__icontains=search_query) | Q(description__icontains=search_query))
    
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
            a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c

        gigs_in_radius = []
        for gig in gigs:
            venue = gig.venue
            if not venue or not venue.location or len(venue.location) < 2:
                continue
                
            try:
                venue_lat, venue_lon = float(venue.location[0]), float(venue.location[1])
                distance = haversine(user_lat, user_lon, venue_lat, venue_lon)
                if distance <= radius:
                    gigs_in_radius.append(gig.id)
            except (ValueError, TypeError):
                continue
                
        gigs = gigs.filter(id__in=gigs_in_radius)
    
    # Order by most recent first
    gigs = gigs.order_by('-created_at')
    
    # Create cache key
    cache_key = f"gig_list_{location}_{radius}_{search_query}_{gig_type}_page_{page}_perpage_{per_page}"
    cached_response = cache.get(cache_key)
    if cached_response:
        return paginator.get_paginated_response(cached_response)
    
    # Paginate and serialize
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
    permission_classes = [IsAuthenticated]
    
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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_venue_event(request):
    """
    Create a new venue event.
    Only venue users can create venue events.
    """
    user = request.user
    
    # Check if user is a venue
    if not hasattr(user, 'venue') or not user.venue:
        return Response(
            {'detail': 'Only venue users with a valid venue can create venue events'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    # Create a mutable copy of the request data
    data = request.data.copy()
    
    # Set required fields for venue event
    data['gig_type'] = GigType.VENUE_GIG
    data['status'] = Status.PENDING
    data['venue'] = user.venue.id
    data['created_by'] = user.id
    
    # Set default values if not provided
    if 'title' not in data:
        data['title'] = f"Event at {user.venue.venue_name}"
    if 'description' not in data:
        data['description'] = f"Event hosted by {user.venue.venue_name}"
    
    # Handle file upload
    if 'flyer_image' in request.FILES:
        data['flyer_image'] = request.FILES['flyer_image']
    
    # Validate capacity against venue limits
    venue = user.venue
    max_artists = int(data.get('max_artists', 1))
    max_tickets = int(data.get('max_tickets', 1))
    
    if max_artists > venue.artist_capacity:
        return Response(
            {'detail': f'Maximum artists cannot exceed venue capacity of {venue.venue_name} which is {venue.artist_capacity} artists'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    if max_tickets > venue.capacity:
        return Response(
            {'detail': f'Maximum tickets cannot exceed venue capacity of {venue.venue_name} which is {venue.capacity} people'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Use the VenueEventSerializer for validation
    serializer = VenueEventSerializer(data=data, context={'request': request})
    
    if serializer.is_valid():
        # Save with the correct gig_type and venue
        gig = serializer.save(
            gig_type=GigType.VENUE_GIG,
            venue=user.venue,
            created_by=user
        )
        
        # Create notification
        create_notification(
            user=user,
            notification_type='venue_event_created',
            message=f'Successfully created venue event: {gig.title}',
            **gig.__dict__
        )
        
        # Use the GigDetailSerializer which includes all necessary fields
        response_serializer = GigDetailSerializer(gig, context={'request': request})
        
        return Response({
            'status': 'success',
            'data': response_serializer.data,
            'message': 'Venue event created successfully'
        }, status=status.HTTP_201_CREATED)
    
    return Response({
        'status': 'error',
        'errors': serializer.errors,
        'message': 'Validation error'
    }, status=status.HTTP_400_BAD_REQUEST)


class LikeGigView(APIView):
    """
    Like or unlike a gig
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, gig_id):
        try:
            gig = Gig.objects.get(id=gig_id)
            user = request.user
            
            if gig.likes.filter(id=user.id).exists():
                gig.likes.remove(user)
                liked = False
            else:
                gig.likes.add(user)
                liked = True
                
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
    List all gigs liked by the current user
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        liked_gigs = request.user.liked_gigs.all()
        serializer = GigSerializer(
            liked_gigs, 
            many=True, 
            context={'request': request}
        )
        return Response({
            'status': 'success',
            'count': liked_gigs.count(),
            'results': serializer.data
        })


class UpcomingGigsView(generics.ListAPIView):
    """
    List all upcoming gigs (both artist and venue gigs)
    """
    serializer_class = GigSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = PageNumberPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend, filters.OrderingFilter]
    search_fields = ['title', 'description', 'venue__name']
    ordering_fields = ['event_date', 'created_at']
    filterset_fields = ['gig_type', 'status']
    
    def get_queryset(self):
        now = timezone.now()
        return Gig.objects.filter(
            event_date__gte=now,
            status='approved'
        ).order_by('event_date')


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_invite_request(request, id):
    user = request.user
    
    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    data = request.data.copy()
    artist = data.get('artist', None)
    
    if artist is None:
        return Response({'detail': 'artist value missing'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
        if gig.user != user:
            return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        artist = Artist.objects.get(id=artist)
        gig_invite = GigInvite.objects.create(gig=gig, user=user, artist_received=artist)
        gig_invite.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    create_notification(request.user, 'system', 'Gig invitation sent', **gig.__dict__)
    return Response({
        'message': 'Gig invitation sent successfully'
    }, status=status.HTTP_201_CREATED)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def accept_invite_request(request, id):
    user = request.user
    
    if user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    owner_id = request.data.get('owner', None)
    
    if owner_id is None:
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
        gig_invite = GigInvite.objects.get(gig=gig, user=owner, artist_received=artist, status='pending')
        if gig_invite is None:
            return Response({'detail': 'Gig invite not found'}, status=status.HTTP_404_NOT_FOUND)
        gig_invite.status = GigInviteStatus.ACCEPTED
        gig_invite.save()
        gig.invitees.add(artist)
        gig.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = GigSerializer(gig)
    
    create_notification(request.user, 'system', 'Gig invite accepted', **gig.__dict__)
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
    owner_id = request.data.get('owner', None)
    
    if owner_id is None:
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
        gig_invite = GigInvite.objects.get(gig=gig, user=owner, artist_received=artist, status='pending')
        if gig_invite is None:
            return Response({'detail': 'Gig invite not found'}, status=status.HTTP_404_NOT_FOUND)
        gig_invite.status = GigInviteStatus.REJECTED
        gig_invite.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = GigSerializer(gig)
    
    create_notification(request.user, 'system', 'Gig invite rejected', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig invite rejected successfully'
    }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_gig(request):
    user = request.user

    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    data = request.data.copy()
    print("data:", data)
    venue_id = data.get('venue_id', None)
    
    try:
        venue = Venue.objects.get(id=venue_id)
        print("venue:", venue)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data['venue'] = venue.id
    data['user'] = user
    if not data.get('max_artist'):
        data['max_artist'] = venue.artist_capacity
    serializer = GigSerializer(data=data, partial=True, context=request)
    if serializer.is_valid():
        gig = serializer.save()
        create_notification(request.user, 'system', 'Gig created successfully', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig created successfully'
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    try:
        gig.is_public = is_public
        gig.save()
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = GigSerializer(gig)
    
    create_notification(request.user, 'system', 'Gig status updated successfully', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig status updated successfully'
    }, status=status.HTTP_201_CREATED)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_gig_details(request, id):
    user = request.user
    
    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        gig = Gig.objects.get(id=id)
        print("gig:", gig)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data.copy()
    # If flyer_bg is present in FILES, add it to data
    if 'flyer_bg' in request.FILES:
        data['flyer_bg'] = request.FILES['flyer_bg']
    max_tickets = int(data.get('max_tickets', 0))
    
    if max_tickets == 0:
        return Response({'detail': 'max_tickets cannot be zero'}, status=status.HTTP_400_BAD_REQUEST)
    print("user", user)
    venue = Venue.objects.get(user_id=user.id)

    if max_tickets > venue.capacity:
        return Response({'detail': 'Max tickets value exceeds venue capacity'}, status=status.HTTP_400_BAD_REQUEST)
    data['max_artist'] = venue.artist_capacity
    
    serializer = GigSerializer(gig, data=data, partial=True, context={"request": request})
    if serializer.is_valid():
        gig = serializer.save()
        create_notification(request.user, 'system', 'Gig created successfully', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig created successfully'
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    venue_fee = data.get('venue_fee', user.venue.venue_fee)
    
    if venue_fee is None:
        return Response({'detail': 'venue_fee value missing'}, status=status.HTTP_400_BAD_REQUEST)
    
    gig.venue_fee = venue_fee
    gig.save()
    
    serializer = GigSerializer(gig)
    
    create_notification(request.user, 'system', 'Gig venue fee updated successfully', **gig.__dict__)
    return Response({
        'gig': serializer.data,
        'message': 'Gig venue fee updated successfully'
    }, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_gig_status(request, id):
    user = request.user
    
    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
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
    
    create_notification(request.user, 'system', 'Gig status updated successfully', **gig.__dict__)
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
    elements.append(Paragraph(f"Venue: {contract.venue.user.name}", content_style))
    elements.append(Paragraph(f"Artist: {contract.artist.user.name}", content_style))
    elements.append(Paragraph(f"Venue Fee: ${contract.price}", content_style))
    elements.append(Paragraph(f"Gig: {contract.gig.name}", content_style))
    elements.append(Paragraph(f"Ticket Price: ${contract.gig.ticket_price}", content_style))
    elements.append(Paragraph(f"Event Date: {contract.gig.event_date.date()}", content_style))
    elements.append(Paragraph(f"Contract Date: {contract.created_at.date()}", content_style))
    
    requests_to_artist = [req for req in contract.request_message.split('. ') if req.strip()]

    elements.append(Spacer(1, 20))
    for req in requests_to_artist:
        elements.append(Paragraph(req, content_style))
    
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
    elements.append(Paragraph("Venue Signature: ________________________", content_style))
    elements.append(Paragraph("Artist Signature: ________________________", content_style))
    
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
    draw.text((50, y), f"Venue: {contract.venue.user.name}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Artist: {contract.artist.user.name}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Venue Fee: ${contract.price}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Gig: {contract.gig.name}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Ticket Price: ${contract.gig.ticket_price}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Event Date: {contract.gig.event_date.date()}", font=font_content, fill=(0, 0, 0)); y += small_spacing
    draw.text((50, y), f"Contract Date: {contract.created_at.date()}", font=font_content, fill=(0, 0, 0)); y += small_spacing

    # Requests to Artist (split at '. ')
    requests_to_artist = [req for req in contract.request_message.split('. ') if req.strip()]
    if requests_to_artist:
        y += 12
        draw.text((50, y), "Requests to Venue:", font=font_content, fill=(0, 0, 0)); y += small_spacing
        for req in requests_to_artist:
            draw.text((70, y), f"- {req}", font=font_content, fill=(0, 0, 0)); y += small_spacing

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
    draw.text((50, y), "Venue Signature: ________________________", font=font_content, fill=(0, 0, 0)); y += small_spacing + 10
    draw.text((50, y), "Artist Signature: ________________________", font=font_content, fill=(0, 0, 0)); y += small_spacing

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
        print(model_to_dict(gig))
        artist = Artist.objects.get(user=gig.user.id)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        venue = Venue.objects.get(id=gig.venue)
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
        return Response({'contract': {'id': contract.id,'artist': artist.user.name, 'venue': venue.user.name, 'gig': gig.name, 'pdf_url': contract.pdf.url, 'image_url': contract.image.url}}, status=status.HTTP_200_OK)
        
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
            contract = Contract.objects.get(id=contract_id, artist=artist)
        except Contract.DoesNotExist:
            return Response({'detail': 'Contract not found'}, status=status.HTTP_404_NOT_FOUND)
    else:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)

    serializer = ContractSerializer(contract)
    return Response({'contract': serializer.data})

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def sign_contract(request, contract_id):
    user = request.user
    contract_pin = request.data.get('contract_pin', None)
    application_fee = int(request.data.get('application_fee', 0))
    is_host = request.data.get('is_host', False)
    
    if not contract_pin:
        return Response({'detail': 'Contract pin is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    if user.contract_pin != contract_pin:
        return Response({'detail': 'Invalid contract pin'}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        contract = Contract.objects.get(id=contract_id, user=user)
        if not contract:
            contract = Contract.objects.get(id=contract_id, recipient=user)
            if not contract:
                return Response({'detail': 'You are not authorized to sign this contract'}, status=status.HTTP_403_FORBIDDEN)
        
        
    except Contract.DoesNotExist:
        return Response({'detail': 'Contract not found'}, status=status.HTTP_404_NOT_FOUND)
    
    contract.signer = user
    contract.is_signed = True
    contract.save()
    if user.role == ROLE_CHOICES.ARTIST:
        # Calculate amounts
        amount = contract.price * 100  # in cents
        application_fee = application_fee * 100  # in cents
        
        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            application_fee_amount=application_fee,
            transfer_data={
                "destination": contract.venue.stripe_account_id,
            },
            metadata={
                "contract_id": contract.id,
                "payment_intent_for": "contract_signature",
                "is_host": is_host
            }
        )
        
        return Response({
            "client_secret": intent.client_secret,
            "payment_intent_id": intent.id
        })  
        
    
    return Response({'detail': 'Contract signed successfully', }, status=status.HTTP_200_OK)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_contract_pin(request):
    user = request.user
    contract_pin = user.gen_contract_pin()

    context = {
        'message': 'Contract Pin generated successfully',
        'contract_pin': contract_pin
    }
    
    send_templated_email(
        subject='Contract Pin Generated',
        recipient_list=[user.email],
        template_name='contract_pin',
        context=context
    )
    
    return Response({'contract_pin': contract_pin}, status=status.HTTP_200_OK)
