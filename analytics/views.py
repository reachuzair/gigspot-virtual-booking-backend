from datetime import timedelta
from django.utils import timezone
from django.db.models import Count, Sum
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db.models.functions import TruncMonth
from gigs.models import Contract, Gig
from django.db.models import F
from decimal import Decimal

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def fan_engagement_stats(request):
    user = request.user
    if not hasattr(user, 'artist_profile'):
        return Response({'detail': 'Only artists can access fan engagement.'}, status=403)

    today = timezone.now().date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    data = []

    for day in days:
        gigs_on_day = Gig.objects.filter(created_by=user, created_at__date=day)

        total_likes = gigs_on_day.annotate(likes_count=Count('likes')).aggregate(
            total=Sum('likes_count'))['total'] or 0

        total_tickets = sum(gig.tickets.count() for gig in gigs_on_day)

        engagement = total_likes + total_tickets

        data.append({
            "day": day.strftime('%a'),
            "date": day.strftime('%Y-%m-%d'),
            "engagement": engagement
        })

    current = data[-1]['engagement'] if data else 0
    highest = max([d['engagement'] for d in data], default=0)

    return Response({
        "daily_data": data,
        "highlight": {
            "note": f"{current} total fan engagements today (likes + tickets)",
            "value": current
        },
        "highest_interaction": highest,
        "current_engagement": current
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def analytics_overview(request):
    user = request.user
    if not hasattr(user, 'artist_profile'):
        return Response({'detail': 'Only artists can view analytics.'}, status=403)

    artist = user.artist_profile

    contracts = Contract.objects.filter(artist_signed=True, artist=artist)
    monthly = contracts.annotate(month=TruncMonth('created_at')) \
        .values('month') \
        .annotate(total=Sum('price')) \
        .order_by('-month')[:2]

    current_month = monthly[0]['total'] if len(monthly) > 0 else 0
    previous_month = monthly[1]['total'] if len(monthly) > 1 else 0

    if previous_month:
        revenue_change = ((current_month - previous_month) /
                          previous_month) * 100
        change_dir = "up" if revenue_change >= 0 else "down"
    else:
        revenue_change = 0
        change_dir = "up"

    profit = Decimal('0.4')
    profit_change = revenue_change 

    return Response({
        "revenue": {
            "amount": int(current_month),
            "change": abs(round(revenue_change, 2)),
            "change_direction": change_dir
        },
        "profit": {
            "amount": int(profit),
            "change": abs(round(profit_change, 2)),
            "change_direction": change_dir
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def ticket_analytics(request):
    user = request.user
    now = timezone.now()

    gigs = Gig.objects.filter(created_by=user)

    gigs = gigs.annotate(ticket_count=Count('tickets'))

    total_tickets = gigs.aggregate(total=Sum('ticket_count'))['total'] or 0
    max_tickets = gigs.aggregate(max=Sum('max_tickets'))['max'] or 0

    revenue = gigs.aggregate(
        total=Sum(F('ticket_count') * F('ticket_price'))
    )['total'] or 0

    gigs_sorted = gigs.order_by('-event_date')
    if gigs_sorted.count() >= 2:
        latest = gigs_sorted[0].ticket_count or 0
        previous = gigs_sorted[1].ticket_count or 1
        percent_change = ((latest - previous) / previous) * 100
    else:
        percent_change = 0

    sales_trend = []
    for day_offset in range(6, -1, -1):
        day = now - timedelta(days=day_offset)
        day_gigs = gigs.filter(event_date__date=day.date())
        day_total = day_gigs.aggregate(total=Sum('ticket_count'))['total'] or 0
        sales_trend.append({
            "date": day.strftime("%d %b"),
            "tickets": day_total
        })

    return Response({
        "total_tickets_sold": total_tickets,
        "max_possible_tickets": max_tickets,
        "revenue_generated": float(revenue),
        "percent_change_from_last_show": round(percent_change, 2),
        "sales_over_time": sales_trend,
        "current_date": now.strftime("%d %b %Y")
    })
