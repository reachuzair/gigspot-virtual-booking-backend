from django.shortcuts import render
from rest_framework.decorators import api_view, permissions_classes
from rest_framework.response import Response
from rest_framework.permissions import AllowAny

# Create your views here.

@api_view(['GET'])
@permissions_classes([AllowAny])
def hello_test(request):
    return Response({"message": "Hello, World!"})