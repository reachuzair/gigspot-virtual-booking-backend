from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Gig, Contract
from custom_auth.models import Venue, ROLE_CHOICES, Artist, User
from rt_notifications.utils import create_notification
from utils.email import send_templated_email
from django.forms.models import model_to_dict
from .serializers import GigSerializer, ContractSerializer
from PIL import Image, ImageDraw, ImageFont
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from rest_framework.pagination import PageNumberPagination
from django.core.cache import cache
# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gigs(request):
    user = request.user
    per_page = request.query_params.get('per_page', 10)
    page = request.query_params.get('page', 1)
    paginator = PageNumberPagination()
    paginator.page_size = per_page

    # Create a unique cache key per user and page
    cache_key = f"gigs_{user.id}_page_{page}_perpage_{per_page}"
    cached_response = cache.get(cache_key)
    if cached_response:
        return paginator.get_paginated_response(cached_response)

    gigs = Gig.objects.filter(user=user)
    result_page = paginator.paginate_queryset(gigs, request)
    serializer = GigSerializer(result_page, many=True)
    cache.set(cache_key, serializer.data, timeout=60*5)  # cache for 5 minutes
    return paginator.get_paginated_response(serializer.data)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def list_gigs(request):
    import math
    user = request.user
    per_page = int(request.query_params.get('per_page', 10))
    page = int(request.query_params.get('page', 1))
    paginator = PageNumberPagination()
    paginator.page_size = per_page

    location = request.query_params.get('location', None)
    radius = int(request.query_params.get('radius', 30))
    search_query = request.query_params.get('search', '')
    gigs = Gig.objects.all()

    # If location is provided, filter gigs within radius miles
    if location:
        try:
            lat_str, lon_str = location.split(',')
            user_lat, user_lon = float(lat_str), float(lon_str)
        except Exception:
            return Response({'detail': 'Invalid location format. Use lat,lon'}, status=status.HTTP_400_BAD_REQUEST)

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
            venue_lat, venue_lon = venue.location[0], venue.location[1]
            try:
                venue_lat, venue_lon = float(venue_lat), float(venue_lon)
            except Exception:
                continue
            distance = haversine(user_lat, user_lon, venue_lat, venue_lon)
            if distance <= radius:
                gigs_in_radius.append(gig)
        gigs = gigs_in_radius

    if search_query:
        gigs = gigs.filter(Q(name__icontains=search_query))

    gigs = gigs.filter(status='approved')
    
    result_page = paginator.paginate_queryset(gigs, request)
    serializer = GigSerializer(result_page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gig(request, id):
    try:
        data = Gig.objects.get(id=id)

        serializer = GigSerializer(data)
        return Response({'gig': serializer.data})
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_gig(request):
    user = request.user

    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    data = request.data.copy()
    venue_id = data.get('venue', None)
    
    try:
        venue = Venue.objects.get(id=venue_id)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data['venue'] = venue
    data['user'] = user
    serializer = GigSerializer(gig, data=data, partial=True)
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
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data.copy()
    # If flyer_bg is present in FILES, add it to data
    if 'flyer_bg' in request.FILES:
        data['flyer_bg'] = request.FILES['flyer_bg']
    max_tickets = data.get('max_tickets', None)
    
    if max_tickets is None:
        return Response({'detail': 'max_tickets value missing'}, status=status.HTTP_400_BAD_REQUEST)

    venue = Venue.objects.get(id=gig.venue)

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

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def update_gig_status(request, id):
    user = request.user
    
    if user.role != ROLE_CHOICES.VENUE and user.role != ROLE_CHOICES.ARTIST:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    data = request.data.copy()
    status = data.get('status', None)
    
    if status is None:
        return Response({'detail': 'status value missing'}, status=status.HTTP_400_BAD_REQUEST)
    
    allowed_status = ['approved', 'rejected']
    if status not in allowed_status:
        return Response({'detail': 'Invalid status'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    try:
        gig.status = status
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
        artist = Artist.objects.get(id=gig.artist)
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
    return Response({'detail': 'Contract signed successfully'}, status=status.HTTP_200_OK)
    

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
