from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Gig, SeatRow, Seat
from custom_auth.models import Venue, ROLE_CHOICES
from rt_notifications.utils import create_notification
from utils.email import send_templated_email
from django.forms.models import model_to_dict
from .serializers import GigSerializer, SeatRowSerializer, SeatSerializer

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gigs(request):
    gigs = Gig.objects.all()
    return Response({'gigs': list(gigs.values())})

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
    
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data.copy()
    data['venue'] = {'id': venue.id}
    data['is_live'] = True
    
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
def update_gig_live_status(request, id):
    try:
        gig = Gig.objects.get(id=id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    is_live = request.data.get('is_live', None)

    if not isinstance(is_live, bool):
        return Response({'detail': 'Invalid live status'}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = GigSerializer(gig, data={'is_live': is_live})
    if serializer.is_valid():
        serializer.save()
        create_notification(request.user, 'system', 'Gig live status updated', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig live status updated successfully'
        }, status=status.HTTP_200_OK)
    
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


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_seat_row(request, gig_id):
    
    user = request.user
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        gig = Gig.objects.get(id=gig_id, venue=venue)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data.copy()
    data['gig'] = gig.id
    
    serializer = SeatRowSerializer(data=data)
    if serializer.is_valid():
        seat_row = serializer.save()
        create_notification(request.user, 'system', 'Seat row created successfully', **seat_row.__dict__)
        return Response({
            'seat_row': serializer.data,
            'message': 'Seat row created successfully'
        }, status=status.HTTP_201_CREATED)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gig_rows(request, gig_id):
    try:
        gig = Gig.objects.get(id=gig_id)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    seat_rows = SeatRow.objects.filter(gig=gig)
    return Response({'seat_rows': list(seat_rows.values())})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_seat_row(request, row_id, gig_id):
    user = request.user
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        gig = Gig.objects.get(id=gig_id, venue=venue)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        seat_row = SeatRow.objects.get(id=row_id, gig=gig)
    except SeatRow.DoesNotExist:
        return Response({'detail': 'Seat row not found'}, status=status.HTTP_404_NOT_FOUND)
    
    seat_row.delete()
    create_notification(request.user, 'system', 'Seat row deleted successfully', **seat_row.__dict__)
    return Response({'message': 'Seat row deleted successfully'}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def add_seats(request, gig_id, row_id):
    user = request.user
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        gig = Gig.objects.get(id=gig_id, venue=venue)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        seat_row = SeatRow.objects.get(id=row_id, gig=gig)
    except SeatRow.DoesNotExist:
        return Response({'detail': 'Seat row not found'}, status=status.HTTP_404_NOT_FOUND)
    
    data = request.data.copy()
    action = data.get('action', None)
    
    if action == 'add_single':
        data['row'] = seat_row.id
        data['name'] = f'{seat_row.name}{len(Seat.objects.filter(row=seat_row)) + 1}'
        data['gig'] = gig.id
        
        serializer = SeatSerializer(data=data)
        if serializer.is_valid():
            seat = serializer.save()
            create_notification(request.user, 'system', 'Seat created successfully', **seat.__dict__)
            return Response({
                'seat': serializer.data,
                'message': 'Seat added successfully'
            }, status=status.HTTP_201_CREATED)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif action == 'add_multiple':
        count = data.get('count', None)
        price = data.get('price', None)
        
        if not isinstance(count, int) or count <= 0:
            return Response({'detail': 'Invalid count'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not price:
            return Response({'detail': 'Invalid price'}, status=status.HTTP_400_BAD_REQUEST)
        
        seats = []
        prev_seats = Seat.objects.filter(row=seat_row)
        for i in range(count):
            seat_data = {
                'row': seat_row,
                'name': f'{seat_row.name}{len(prev_seats) + i + 1}',
                'price': float(price),
                'gig': gig
            }
            seats.append(Seat(**seat_data))
        
        Seat.objects.bulk_create(seats)
        create_notification(request.user, 'system', 'Seats created successfully', **seats[0].__dict__)
        
        # Serialize the seats using SeatSerializer
        serialized_seats = SeatSerializer(seats, many=True).data
        return Response({
            'seats': serialized_seats,
            'message': 'Seats added successfully'
        }, status=status.HTTP_201_CREATED)
    
    else:
        return Response({'detail': 'Invalid or No action provided'}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_seats(request, gig_id, row_id):
    try:
        seat_row = SeatRow.objects.get(id=row_id)
    except SeatRow.DoesNotExist:
        return Response({'detail': 'Seat row not found'}, status=status.HTTP_404_NOT_FOUND)
    
    seats = Seat.objects.filter(row=seat_row)
    return Response({'seats': list(seats.values())})

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_seat(request, gig_id):
    user =request.user
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'detail': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'detail': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        gig = Gig.objects.get(id=gig_id, venue=venue)
    except Gig.DoesNotExist:
        return Response({'detail': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    seat_id_list = request.data.get('seat_id_list', None)
    if not seat_id_list:
        return Response({'detail': 'Invalid seat ID'}, status=status.HTTP_400_BAD_REQUEST)
    
    seats = []
    for seat_id in seat_id_list:
        try:
            seat = Seat.objects.get(id=seat_id, gig=gig)
            seats.append(seat)
        except Seat.DoesNotExist:
            return Response({'detail': 'Seat not found'}, status=status.HTTP_404_NOT_FOUND)
        
        seat.delete()
    
    create_notification(request.user, 'system', 'Seats deleted successfully', **seats[0].__dict__)
    return Response({'message': 'Seats deleted successfully'}, status=status.HTTP_200_OK)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_contract_pin(request):
    user = request.user
    contract_pin = user.gen_contract_pin()

    context = {
        'message': 'Contract Pin generated successfully',
        'contract_pin': contract_pin
    }
    create_notification(request.user, 'system', 'Contract Pin generated successfully', **user.__dict__)
    
    send_templated_email(
        subject='Contract Pin Generated',
        recipient_list=[user.email],
        template_name='contract_pin',
        context=context
    )
    
    return Response({'contract_pin': contract_pin}, status=status.HTTP_200_OK)
