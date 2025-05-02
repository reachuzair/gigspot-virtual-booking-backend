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
def get_gig(request, id):
    try:
        data = Gig.objects.get(id=id)

        serializer = GigSerializer(data)
        return Response({'gig': serializer.data})
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_gig(request):
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
    
    serializer = GigSerializer(data=data)
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
def update_gig(request, id):
    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    key = request.data.get('key', None)
    value = request.data.get('value', None)

    if not key or not value:
        return Response({'detail': 'Invalid key or value'}, status=status.HTTP_400_BAD_REQUEST)

    allowed_keys = ['name', 'description', 'startDate', 'endDate', 'eventStartDate', 'eventEndDate', 'max_artist', 'flyer_text']
    if key not in allowed_keys:
        return Response({'detail': 'Invalid key'}, status=status.HTTP_400_BAD_REQUEST)
    
    if key == 'is_live':
        return update_gig_live_status(request, id)

    serializer = GigSerializer(gig, data={key: value})
    if serializer.is_valid():
        serializer.save()
        create_notification(request.user, 'system', 'Gig updated successfully', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig updated successfully'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

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
    elements.append(Paragraph(f"Price: ${contract.price}", content_style))
    elements.append(Paragraph(f"Date: {contract.created_at.date()}", content_style))
    
    # Add terms and conditions
    terms = [
        "Terms and Conditions:",
        "1. The artist agrees to perform the services as described.",
        "2. The recipient agrees to pay the agreed amount.",
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
    image = Image.new('RGB', (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    # Add contract content
    draw.text((50, 50), "CONTRACT AGREEMENT", font=font, fill=(0, 0, 0))
    draw.text((50, 100), f"Venue: {contract.venue.user.name}", font=font, fill=(0, 0, 0))
    draw.text((50, 130), f"Artist: {contract.artist.user.name}", font=font, fill=(0, 0, 0))
    draw.text((50, 160), f"Price: ${contract.price}", font=font, fill=(0, 0, 0))
    draw.text((50, 190), f"Date: {contract.created_at.date()}", font=font, fill=(0, 0, 0))
    
    # Add terms and conditions
    terms = [
        "Terms and Conditions:",
        "1. The artist agrees to perform the services as described.",
        "2. The recipient agrees to pay the agreed amount.",
        "3. Any changes must be agreed upon by both parties.",
        "4. This contract is legally binding."
    ]
    
    y_position = 250
    for term in terms:
        draw.text((50, y_position), term, font=font, fill=(0, 0, 0))
        y_position += 30
    
    # Add signatures placeholder
    draw.text((50, 450), "Venue Signature: ________________________", font=font, fill=(0, 0, 0))
    draw.text((50, 500), "Artist Signature: ________________________", font=font, fill=(0, 0, 0))
    
    # Save the image to BytesIO
    image_io = io.BytesIO()
    image.save(image_io, format='PNG')
    
    return image_io

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_contract(request):
    user = request.user
    artist = request.data.get('artist', None)
    price = request.data.get('price', None)
    gig = request.data.get('gig', None)
    
    if not artist or not price or not gig:
        return Response({'detail': 'Invalid artist or price or gig'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        artist = Artist.objects.get(id=artist)
    except Artist.DoesNotExist:
        return Response({'detail': 'Artist not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        venue = Venue.objects.get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        gig = Gig.objects.get(id=gig)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        # Create a new contract (adjust fields as needed)
        contract = Contract.objects.create(
            artist=artist,  # assuming user has an artist profile
            venue=venue,  # assuming you pass venue_id in request
            price=price,
            gig=gig
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
        return Response({'contract': {'id': contract.id,'artist': artist.user.name, 'venue': venue.user.name, 'gig': gig.name, 'price': contract.price, 'pdf_url': contract.pdf.url, 'image_url': contract.image.url}}, status=status.HTTP_200_OK)
        
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
