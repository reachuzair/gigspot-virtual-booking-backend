# views.py
from rest_framework import generics, filters
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from custom_auth.models import Venue
from users.serializers import VenueProfileSerializer
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination

import django_filters


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


class VenueListView(generics.ListAPIView):
    queryset = Venue.objects.all().order_by('-created_at')
    serializer_class = VenueProfileSerializer
    filter_backends = [filters.SearchFilter,
                       filters.OrderingFilter, DjangoFilterBackend]
    filterset_class = VenueFilter

    search_fields = ['venue_name', 'venue_email', 'venue_phone']
    ordering_fields = ['created_at', 'updated_at', 'capacity']

class VenueDetailView(generics.RetrieveAPIView):
    queryset = Venue.objects.all()
    serializer_class = VenueProfileSerializer
    lookup_field = 'id'