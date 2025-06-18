from rest_framework import generics, filters, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
import django_filters
from django.db.models import Count, F, ExpressionWrapper, fields, Q
from django.utils import timezone
from datetime import timedelta

from custom_auth.models import Venue, User
from users.serializers import VenueProfileSerializer
from gigs.models import Gig, Status


class VenueFilter(django_filters.FilterSet):
    """
    FilterSet for Venue model with city and state filtering
    """
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
    """
    Pagination class for venue listings
    """
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class VenueListView(generics.ListAPIView):
    """
    List all venues with filtering and search capabilities
    """
    queryset = Venue.objects.all().order_by('-created_at')
    serializer_class = VenueProfileSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter, DjangoFilterBackend]
    filterset_class = VenueFilter
    permission_classes = [AllowAny]
    pagination_class = VenuePagination
    search_fields = ['venue_name', 'venue_email', 'venue_phone']
    ordering_fields = ['created_at', 'updated_at', 'capacity']


class VenueDetailView(generics.RetrieveAPIView):
    """
    Retrieve detailed information about a specific venue
    """
    queryset = Venue.objects.all()
    serializer_class = VenueProfileSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'


class VenueAnalyticsView(APIView):
    """
    API endpoint to get analytics for the current user's venue shows
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Get the venue associated with the current user
            if not hasattr(request.user, 'venue'):
                return Response(
                    {"error": "No venue associated with this user account"},
                    status=status.HTTP_403_FORBIDDEN
                )
            
            venue = request.user.venue

            # Get all completed gigs for this venue, ordered by event date
            completed_gigs = Gig.objects.filter(
                venue=venue,
                status=Status.APPROVED,
                event_date__lt=timezone.now()
            ).order_by('event_date')

            # Calculate attendance data for each show
            shows_data = []
            for i, gig in enumerate(completed_gigs):
                # For demo purposes, we'll generate attendance data
                # In a real implementation, you would get this from your ticketing system
                attendance = self._generate_attendance_data(gig, i)
                
                show_data = {
                    'id': gig.id,
                    'title': gig.title,
                    'event_date': gig.event_date,
                    'attendance': attendance,
                    'capacity': gig.max_tickets or 100,  # Default to 100 if not set
                }
                shows_data.append(show_data)

            # Calculate comparison metrics if we have at least 2 shows
            if len(shows_data) >= 2:
                for i in range(1, len(shows_data)):
                    prev_attendance = shows_data[i-1]['attendance']
                    curr_attendance = shows_data[i]['attendance']
                    if prev_attendance > 0:
                        change_pct = ((curr_attendance - prev_attendance) / prev_attendance) * 100
                        shows_data[i]['attendance_change_pct'] = round(change_pct, 1)

            return Response({
                'venue_id': venue.id,
                'venue_name': venue.user.name if venue.user.name else 'Unnamed Venue',
                'total_shows': len(shows_data),
                'shows': shows_data[-3:],  # Return only the last 3 shows for the chart
                'total_attendance': sum(show['attendance'] for show in shows_data) if shows_data else 0,
                'average_attendance': sum(show['attendance'] for show in shows_data) / len(shows_data) if shows_data else 0,
            })

        except Venue.DoesNotExist:
            return Response(
                {"error": "Venue not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _generate_attendance_data(self, gig, index):
        """
        Generate realistic attendance data for demonstration purposes.
        In a real implementation, this would come from your ticketing system.
        """
        # Base attendance on some attributes of the gig
        base_attendance = (gig.max_tickets or 100) * 0.7  # 70% of capacity as base
        
        # Add some variation based on the index to show changes over time
        variation = [0.8, 1.2, 1.0][index % 3]  # Cycle through some variation
        
        # Add some random noise
        import random
        noise = random.uniform(0.9, 1.1)
        
        # Calculate final attendance
        attendance = int(base_attendance * variation * noise)
        
        # Ensure we don't exceed capacity
        max_capacity = gig.max_tickets or 100
        return min(attendance, max_capacity)
