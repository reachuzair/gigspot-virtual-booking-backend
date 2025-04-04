from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .models import Gig
from custom_auth.models import Venue, ROLE_CHOICES
from rt_notifications.utils import create_notification
from django.forms.models import model_to_dict
from .serializers import GigSerializer

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gigs(request):
    gigs = Gig.objects.all()
    return Response({'gigs': list(gigs.values())})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_gig(request, id):
    gig = Gig.objects.get(id=id)
    return Response({'gig': model_to_dict(gig)})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_gig(request):
    user = request.user
    
    if user.role != ROLE_CHOICES.VENUE:
        return Response({'error': 'Unauthorized'}, status=status.HTTP_401_UNAUTHORIZED)
    
    try:
        venue = Venue.objects.select_related('user').get(user=user)
    except Venue.DoesNotExist:
        return Response({'error': 'Venue not found'}, status=status.HTTP_404_NOT_FOUND)
    
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
        return Response({'error': 'Gig not found'}, status=status.HTTP_404_NOT_FOUND)
    
    is_live = request.data.get('is_live', None)

    if not isinstance(is_live, bool):
        return Response({'error': 'Invalid live status'}, status=status.HTTP_400_BAD_REQUEST)
    
    serializer = GigSerializer(gig, data={'is_live': not is_live})
    if serializer.is_valid():
        serializer.save()
        create_notification(request.user, 'system', 'Gig live status updated', **gig.__dict__)
        return Response({
            'gig': serializer.data,
            'message': 'Gig live status updated successfully'
        }, status=status.HTTP_200_OK)
    
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
