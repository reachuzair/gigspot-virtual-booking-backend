from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from .soundcharts import SoundsChartAPI

# Create your views here.

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_artist_by_name(request):

    artist_name = request.query_params.get('artist_name', '')
    soundschart = SoundsChartAPI()

    result = soundschart.search_artist_by_name(artist_name)
    return Response(result, status=status.HTTP_200_OK)