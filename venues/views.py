from rest_framework import generics, filters, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.pagination import PageNumberPagination
import django_filters
from django.db.models import Count, F, ExpressionWrapper, fields, Q, Sum, Case, When, IntegerField
from django.db.models.functions import TruncDate, TruncMonth, TruncDay
from django.utils import timezone
from datetime import date, datetime, time, timedelta
from rest_framework.parsers import MultiPartParser, FormParser
from custom_auth.models import Venue, User
from users.serializers import VenueProfileSerializer
from gigs.models import Gig, Status
from payments.models import Ticket
from venues.models import VenueProof
from venues.serializers import VenueProofSerializer
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.timezone import make_aware
from calendar import monthrange
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
    queryset = Venue.objects.filter(is_completed=True).order_by('-created_at')
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
            now = timezone.now()
            completed_gigs = Gig.objects.filter(
                venue=venue,
                status=Status.APPROVED,
                event_date__lt=now
            ).annotate(
                tickets_sold=Count('tickets', distinct=True),
                total_revenue=Sum('tickets__gig__ticket_price')
            ).order_by('event_date')
            
            # Filter out gigs with no tickets sold
            completed_gigs = [gig for gig in completed_gigs if gig.tickets_sold > 0]

            # Calculate ticket sales data for each show
            shows_data = []
            total_tickets_sold = 0
            total_revenue = 0
            
            for i, gig in enumerate(completed_gigs):
                tickets_sold = gig.tickets_sold or 0
                revenue = gig.total_revenue or 0
                
                show_data = {
                    'id': gig.id,
                    'title': gig.title,
                    'event_date': gig.event_date,
                    'attendance': self._generate_attendance_data(gig, i),
                    'capacity': gig.max_tickets or 100,
                    'tickets_sold': tickets_sold,
                    'ticket_price': float(gig.ticket_price) if gig.ticket_price else 0,
                    'revenue': float(revenue) if revenue else 0,
                    'occupancy_rate': min(round((tickets_sold / (gig.max_tickets or 100)) * 100, 1) if gig.max_tickets else 0, 100)
                }
                
                # Calculate percentage change from previous show
                if i > 0 and shows_data[i-1]['tickets_sold'] > 0:
                    prev_tickets = shows_data[i-1]['tickets_sold']
                    change_pct = ((tickets_sold - prev_tickets) / prev_tickets) * 100
                    show_data['sales_change_pct'] = round(change_pct, 1)
                
                shows_data.append(show_data)
                total_tickets_sold += tickets_sold
                total_revenue += revenue

            # Calculate sales trend over time (last 12 months)
            one_year_ago = timezone.now() - timedelta(days=365)
            monthly_sales = Ticket.objects.filter(
                gig__venue=venue,
                created_at__gte=one_year_ago
            ).annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                tickets_sold=Count('id'),
                monthly_revenue=Sum('gig__ticket_price')
            ).order_by('month')

            # Generate all months in the last year to ensure we have entries for months with no sales
            current_month = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            months = [current_month - timedelta(days=30 * i) for i in range(12)]
            months.reverse()
            
            # Create a dictionary of sales by month
            sales_by_month = {
                sale['month'].replace(day=1): {
                    'tickets_sold': sale['tickets_sold'],
                    'revenue': float(sale['monthly_revenue'] or 0)
                } for sale in monthly_sales
            }
            
            # Create the sales trend with all months, filling in zeros where needed
            sales_trend = [{
                'date': month.strftime('%b %Y'),
                'tickets_sold': sales_by_month.get(month, {'tickets_sold': 0})['tickets_sold'],
                'revenue': sales_by_month.get(month, {'revenue': 0})['revenue']
            } for month in months]

            # Calculate metrics
            num_shows = len(completed_gigs)
            total_tickets_sold = sum(gig.tickets_sold for gig in completed_gigs) if completed_gigs else 0
            total_revenue = sum(float(gig.total_revenue or 0) for gig in completed_gigs) if completed_gigs else 0
            avg_ticket_price = round(total_revenue / total_tickets_sold, 2) if total_tickets_sold > 0 else 0
            total_attendance = sum(show['attendance'] for show in shows_data) if shows_data else 0
            avg_attendance = total_attendance / num_shows if num_shows > 0 else 0

            # Prepare top performing shows (sort by revenue, then by tickets sold)
            top_shows = sorted(
                shows_data,
                key=lambda x: (x['revenue'], x['tickets_sold']),
                reverse=True
            )[:5]  # Top 5 shows

            # Calculate percentage change from previous show for each show
            for i in range(1, len(shows_data)):
                prev_tickets = shows_data[i-1]['tickets_sold']
                current_tickets = shows_data[i]['tickets_sold']
                if prev_tickets > 0:
                    change_pct = ((current_tickets - prev_tickets) / prev_tickets) * 100
                    shows_data[i]['sales_change_pct'] = round(change_pct, 1)
                else:
                    shows_data[i]['sales_change_pct'] = 100.0  # Infinite growth from 0

            # Add change percentage for the most recent show to summary
            latest_show_change = shows_data[-1]['sales_change_pct'] if len(shows_data) > 1 and 'sales_change_pct' in shows_data[-1] else None
            
            # Get current year
            current_year = timezone.now().year
            
            # Create a list of all months in the current year with timezone awareness
            all_months = [
                timezone.make_aware(datetime(current_year, month, 1))
                for month in range(1, 13)
            ]
            
            # Get all ticket sales for the current year, grouped by month
            monthly_sales = Ticket.objects.filter(
                gig__venue=venue,
                created_at__year=current_year
            ).annotate(
                month=TruncMonth('created_at')
            ).values('month').annotate(
                tickets_sold=Count('id'),
                revenue=Sum('gig__ticket_price')
            ).order_by('month')
            
            # Convert to a dictionary for easier lookup
            sales_by_month = {}
            for sale in monthly_sales:
                # Keep the timezone-aware datetime for comparison
                month_date = sale['month']
                sales_by_month[month_date] = {
                    'tickets_sold': sale['tickets_sold'],
                    'revenue': float(sale['revenue'] or 0)
                }
            
            # Debug info
            print("\n--- DEBUG: Monthly Sales Data ---")
            print(f"Venue ID: {venue.id}")
            print(f"Current Year: {current_year}")
            print(f"Found {len(sales_by_month)} months with data")
            for month, data in sales_by_month.items():
                print(f"  - {month.strftime('%b %Y')}: {data['tickets_sold']} tickets, ${data['revenue']}")
            print("--- END DEBUG ---\n")
            
            # Initialize monthly sales data with all months
            monthly_sales_data = []
            previous_month_tickets = 0
            
            for i, month_start in enumerate(all_months):
                # Get sales data for this month or use zeros if no data
                month_data = sales_by_month.get(month_start, {'tickets_sold': 0, 'revenue': 0})
                tickets_sold = month_data['tickets_sold']
                revenue = month_data['revenue']
                
                # Calculate percentage change from previous month
                if i > 0 and previous_month_tickets > 0 and tickets_sold > 0:
                    change_pct = ((tickets_sold - previous_month_tickets) / previous_month_tickets) * 100
                else:
                    change_pct = 0.0
                
                monthly_sales_data.append({
                    'month': month_start.strftime('%b %Y'),
                    'tickets_sold': tickets_sold,
                    'revenue': float(revenue) if revenue else 0.0,
                    'percentage_change': round(change_pct, 2)
                })
                
                # Only update previous_month_tickets if we have data for this month
                if tickets_sold > 0:
                    previous_month_tickets = tickets_sold

            # Return only the monthly sales data
            return Response({
                'monthly_sales': monthly_sales_data
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


class VenueProofUploadView(generics.CreateAPIView):
    """
    GET  → return the latest proof for the venue
    POST → upload a new proof (document or URL)
    """
    serializer_class = VenueProofSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def _get_user_venue(self):
        venue = getattr(self.request.user, "venue_profile", None)
        if not venue:
            raise PermissionDenied("User is not linked to a venue.")
        return venue

    def perform_create(self, serializer):
        venue = self._get_user_venue()
        serializer.save(venue=venue)

    def get(self, request, *args, **kwargs):
        venue = self._get_user_venue()
        latest_proof = VenueProof.objects.filter(venue=venue).order_by('-uploaded_at').first()

        if not latest_proof:
            return Response({"detail": "No proof uploaded yet."}, status=status.HTTP_404_NOT_FOUND)

        serializer = self.get_serializer(latest_proof)
        return Response(serializer.data)
    
class TicketSalesAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        venue = Venue.objects.filter(user=request.user).first()
        if not venue:
            return Response({"detail": "Venue not found."}, status=status.HTTP_404_NOT_FOUND)

        gigs = Gig.objects.filter(venue=venue).order_by('-event_date').prefetch_related('tickets')

        results = []
        for gig in gigs:
            sold_tickets = gig.tickets.filter(price__gt=0).count()
            results.append({
                "id": gig.id,
                "flyer_image": gig.flyer_image.url if gig.flyer_image else None,
                "event_title": gig.title,
                "event_date": gig.event_date.strftime('%a, %d %b'),
                "time": gig.event_date.strftime('%I:%M %p'),
                "location": gig.venue.city if gig.venue else "",
                "tickets_sold": sold_tickets,
                "total_tickets": gig.max_tickets,
            })

        return Response({"results": results})

class ArtistBillsAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        gigs = Gig.objects.filter(created_by=request.user, venue__isnull=False).select_related('venue')

        results = []
        for gig in gigs:
            results.append({
                "event_title": gig.title,
                "venue_name": gig.venue.user.name if gig.venue and gig.venue.user else "N/A",
                "paid_status": "paid",  # assuming always paid when gig is created
                "amount": float(gig.venue_fee or 0),
                "flyer_image": gig.flyer_image.url if gig.flyer_image else None,
            })

        return Response({"results": results})

class GigDailySalesBreakdownAPI(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, gig_id):
        gig = get_object_or_404(Gig, id=gig_id)

        # Get query parameters or fallback to current values
        today = datetime.today()
        month = int(request.query_params.get('month', today.month))
        year = int(request.query_params.get('year', today.year))
        week_number = int(request.query_params.get('week', 1))

        # WEEKLY SALES (DAILY BREAKDOWN)
        first_day_of_month = date(year, month, 1)
        start_of_week = first_day_of_month + timedelta(days=(week_number - 1) * 7)
        end_of_week = start_of_week + timedelta(days=6)

        daily_sales = []
        for i in range(7):
            day_date = start_of_week + timedelta(days=i)
            tickets_sold = Ticket.objects.filter(
                gig=gig,
                created_at__date=day_date
            ).count()

            daily_sales.append({
                "day": day_date.day,
                "tickets_sold": tickets_sold,
                "total_tickets": gig.max_tickets
            })

        week_range = f"{start_of_week.strftime('%A')} {start_of_week.day} - {end_of_week.strftime('%A')} {end_of_week.day}"

        weekly_sales = {
            "gig_id": gig.id,
            "title": gig.title,
            "week_range": week_range,
            "daily_sales": daily_sales
        }

        # MONTHLY SALES (WEEKLY BREAKDOWN)
        days_in_month = monthrange(year, month)[1]

        monthly_weekly_sales = []
        for week_start_day in range(1, days_in_month + 1, 7):
            start_date = date(year, month, week_start_day)
            end_day = min(week_start_day + 6, days_in_month)
            end_date = date(year, month, end_day)

            start_datetime = make_aware(datetime.combine(start_date, time.min))
            end_datetime = make_aware(datetime.combine(end_date, time.max))

            tickets_sold = Ticket.objects.filter(
                gig=gig,
                created_at__range=(start_datetime, end_datetime)
            ).count()

            monthly_weekly_sales.append({
                "week_number": (week_start_day - 1) // 7 + 1,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "tickets_sold": tickets_sold,
                "total_tickets": gig.max_tickets
            })

        monthly_sales = {
            "gig_id": gig.id,
            "title": gig.title,
            "month": first_day_of_month.strftime('%B'),
            "weekly_sales": monthly_weekly_sales
        }

        # Final Combined Response
        return Response({
            "weekly": weekly_sales,
            "monthly": monthly_sales
        })