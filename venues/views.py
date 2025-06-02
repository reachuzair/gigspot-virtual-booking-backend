from rest_framework import generics, filters, status, serializers
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
import django_filters

from .models import Event
from .serializers import EventSerializer
from custom_auth.models import Venue
from users.serializers import VenueProfileSerializer
from rest_framework.views import APIView

class VenueFilter(django_filters.FilterSet):
    city = django_filters.CharFilter(method='filter_city')
    state = django_filters.CharFilter(method='filter_state')

    class Meta:
        model = Venue
        fields = ['is_completed', 'artist_capacity'] 

    def filter_city(self, queryset, name, value):
        return queryset.filter(
            location__isnull=False
        ).filter(
            id__in=[
                venue.id for venue in queryset
                if any(value.lower() in str(loc).lower() for loc in venue.location)
            ]
        )

    def filter_state(self, queryset, name, value):
        return queryset.filter(location__state__icontains=value)


class VenuePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class EventListCreateView(generics.ListCreateAPIView):
    """
    List all events or create a new event
    """
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['title']
    ordering_fields = ['created_at', 'booking_start', 'booking_end']
    
    def get_queryset(self):

        queryset = Event.objects.all().order_by('-created_at')
        return queryset
    
    def list(self, request, *args, **kwargs):
        """
        List all events with proper response format
        """
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
                
            serializer = self.get_serializer(queryset, many=True)
            return Response({
                'status': 'success',
                'data': serializer.data,
                'message': 'Events retrieved successfully'
            })
        except Exception as e:
            return Response(
                {'status': 'error', 'message': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def create(self, request, *args, **kwargs):
        """
        Create a new event with the current user as the creator
        """
        try:
            # Create a mutable copy of the request data
            data = request.data.copy()
            
            # Handle file upload
            if 'flyer_image' in request.FILES:
                data['flyer_image'] = request.FILES['flyer_image']
            
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            
            # Save the instance
            instance = serializer.save()
            
            # Get the serialized data with proper URL handling
            response_serializer = self.get_serializer(instance)
            response_data = response_serializer.data
            
            # Ensure we're returning the correct path format
            if response_data.get('flyer_image'):
                # The serializer will handle the URL formatting
                pass
            
            print("Response data:", response_data)
            
            # Prepare the success response
            headers = self.get_success_headers(response_data)
            return Response(
                {
                    'status': 'success',
                    'data': response_data,
                    'message': 'Event created successfully'
                },
                status=status.HTTP_201_CREATED,
                headers=headers
            )
            
        except serializers.ValidationError as e:
            return Response({
                'status': 'error',
                'errors': e.detail,
                'message': 'Validation error'
            }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def perform_create(self, serializer):
        """
        Save the event with the current user as the creator
        """
        serializer.save(created_by=self.request.user)


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete an event
    """
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    
    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response({
            'status': 'success',
            'data': serializer.data,
            'message': 'Event retrieved successfully'
        })
    
    def destroy(self, request, *args, **kwargs):
        """
        Delete an event and its associated image file
        """
        instance = self.get_object()
        event_id = instance.id
        
        self.perform_destroy(instance)
        
        # Return success response
        return Response(
            {
                'status': 'success',
                'message': 'Event deleted successfully',
                'data': {'id': event_id}
            },
            status=status.HTTP_200_OK
        )


class UpcomingEventsView(generics.ListAPIView):
    """
    List all upcoming events (booking_end is in the future)
    """
    serializer_class = EventSerializer
    permission_classes = [AllowAny]
    
    def get_queryset(self):
        return Event.objects.filter(booking_end__gt=timezone.now()).order_by('booking_start')


class VenueListView(generics.ListAPIView):
    queryset = Venue.objects.all().order_by('-created_at')
    serializer_class = VenueProfileSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    filterset_class = VenueFilter
    permission_classes = [AllowAny]
    search_fields = ['venue_name', 'venue_email', 'venue_phone']
    ordering_fields = ['created_at', 'updated_at', 'capacity']

class VenueDetailView(generics.RetrieveAPIView):
    queryset = Venue.objects.all()
    serializer_class = VenueProfileSerializer
    lookup_field = 'id'


class LikeEventView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, event_id):
        try:
            event = Event.objects.get(pk=event_id)

            if request.user in event.likes.all():
                event.likes.remove(request.user)
                return Response({'status': 'success', 'message': 'Event unliked'}, status=status.HTTP_200_OK)
            else:
                event.likes.add(request.user)
                return Response({'status': 'success', 'message': 'Event liked'}, status=status.HTTP_201_CREATED)

        except Event.DoesNotExist:
            return Response({'status': 'error', 'message': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class UserLikedEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        liked_events = request.user.liked_events.all()  
        from .serializers import EventSerializer
        serializer = EventSerializer(liked_events, many=True)
        return Response({
            'status': 'success',
            'data': serializer.data,
            'message': 'Liked events retrieved successfully'
        }, status=status.HTTP_200_OK)