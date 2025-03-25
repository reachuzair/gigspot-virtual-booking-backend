from django.shortcuts import render
from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status
from .email import send_templated_email

@api_view(['POST'])
@permission_classes([AllowAny])
def send_test_email(request):
    try:
        
        recipient_email= request.data.get('email')
        
        send_templated_email(
            subject="Test Email",
            recipient_list=[recipient_email],
            template_name="base",
            context={}
        )
        return Response({"message": "Email sent successfully"}, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)